# -*- coding: utf-8 -*-
"""
downloader.py —— 多线程分块下载模块

提供 Downloader 类，支持：
    - 多线程分块下载（Range 请求，1~16 线程）
    - 断点续传（进度保存在 .part 文件中，可跨实例续传）
    - 暂停 / 恢复（pause / resume）
    - 可选限速（speed_limit，MB/s）
    - 进度回调 on_progress(current, total) 与状态回调 on_status(msg)

断点续传设计：
    - 每个分块线程写入独立临时文件 save_path.part.<i>；
    - save_path.part.meta 记录线程数与文件总大小，保证跨实例、
      不同线程数时续传仍然正确；
    - 下载完成后把所有分块合并为 save_path，并删除 .part 文件；
    - 服务器不支持 Range 时自动降级为单线程流式下载
      （写入 save_path.part，完成后改名）。

注意：on_progress / on_status 回调在工作线程中执行；GUI 使用时应
通过“队列 + after() 轮询”转发到主线程再更新界面。
"""
import json
import os
import shutil
import threading
import time

try:
    import requests
except ImportError:
    requests = None  # 未安装时由 __init__ 给出明确提示


class Downloader:
    """多线程分块下载器。"""

    CHUNK_SIZE = 64 * 1024      # 每次网络读取的块大小（64KB）
    REPORT_INTERVAL = 0.2       # 进度回调最短时间间隔（秒）

    def __init__(self, url, save_path, threads=4, speed_limit=None,
                 on_progress=None, on_status=None):
        """
        :param url:         下载地址
        :param save_path:   保存路径（最终文件）
        :param threads:     线程数，1~16（越界自动收敛）
        :param speed_limit: 限速（MB/s），None 或 <=0 表示不限速
        :param on_progress: 进度回调 on_progress(current_bytes, total_bytes)
        :param on_status:   状态回调 on_status(message)
        """
        if requests is None:
            raise RuntimeError(
                "未安装 requests 库，无法使用多线程下载。\n"
                "请先执行：pip install requests")

        self.url = url
        self.save_path = save_path
        try:
            self.threads = max(1, min(int(threads), 16))
        except (TypeError, ValueError):
            self.threads = 4
        # 速度限制：MB/s -> 字节/秒；非正数视为不限速
        try:
            self.speed_limit = float(speed_limit) if speed_limit else None
            if self.speed_limit is not None and self.speed_limit <= 0:
                self.speed_limit = None
        except (TypeError, ValueError):
            self.speed_limit = None
        self._bytes_per_sec = (self.speed_limit or 0) * 1024 * 1024

        self.on_progress = on_progress
        self.on_status = on_status

        self.session = requests.Session()   # 复用连接
        self.total_size = None              # 文件总大小（字节）
        self._state = "idle"                # idle/starting/running/paused/finished/error/stopped
        self._pause_event = threading.Event()
        self._pause_event.set()             # set=运行，clear=暂停
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._completed_bytes = 0           # 本次会话已写入的字节数
        self._baseline_bytes = 0            # 启动时 part 文件已有的字节数
        self._last_report = 0.0             # 上次进度回调时间
        self._controller = None             # 控制器线程

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    @property
    def state(self):
        """当前状态：idle/starting/running/paused/finished/error/stopped"""
        return self._state

    def is_busy(self):
        """是否仍在工作（用于 GUI 判断轮询与按钮状态）。"""
        return self._state in ("starting", "running", "paused")

    def start(self):
        """开始下载；若已有 .part 进度则自动断点续传。

        若当前处于暂停状态，则等价于 resume()。
        """
        if self._state in ("running", "starting"):
            self._emit_status("下载正在进行中……")
            return
        if self._state == "paused":
            self.resume()
            return
        # idle / finished / error / stopped：重新启动（基于 .part 续传）
        self._pause_event.set()
        self._stop_event.clear()
        self._state = "starting"
        self._controller = threading.Thread(target=self._run, daemon=True)
        self._controller.start()

    def pause(self):
        """暂停下载：各线程停止写入，进度保存在 .part 文件中。"""
        if self._state not in ("running", "starting"):
            self._emit_status("当前没有正在进行的下载")
            return
        self._state = "paused"
        self._pause_event.clear()
        self._emit_status(
            f"已暂停，进度已保存（{self._fmt(self._baseline_bytes + self._completed_bytes)}）")

    def resume(self):
        """恢复下载（从暂停位置继续）。"""
        if self._state != "paused":
            self._emit_status("当前没有处于暂停状态的下载")
            return
        self._state = "running"
        self._pause_event.set()
        self._emit_status("已恢复下载")

    def stop(self):
        """停止下载（保留 .part 文件，之后可重新续传）。"""
        self._stop_event.set()
        self._pause_event.set()
        if self._state in ("running", "starting", "paused"):
            self._state = "stopped"
            self._emit_status("已停止下载")
        # 等待控制器（连同各工作线程）完全退出，
        # 避免仍有线程占用 .part 文件导致后续续传/合并失败
        if self._controller and self._controller.is_alive():
            self._controller.join(timeout=10)

    # ------------------------------------------------------------------
    # 控制器线程：获取文件信息 → 分块 → 启动工作线程 → 合并
    # ------------------------------------------------------------------
    def _run(self):
        try:
            total, supports_range = self._fetch_total_size()
            if total is None:
                self._emit_status("无法获取文件大小，改用单线程流式下载")
                self._single_stream_download(None)
                return
            self.total_size = total

            # 目标文件已完整存在：直接完成
            if os.path.exists(self.save_path) \
                    and os.path.getsize(self.save_path) == total:
                self._state = "finished"
                self._emit_status(f"文件已存在且完整，无需下载：{self.save_path}")
                self._emit_progress(total, total)
                return

            if not supports_range:
                self._emit_status("服务器不支持断点续传，使用单线程下载")
                self._single_stream_download(total)
                return

            # 断点续传：读取/写入元信息（线程数、总大小）
            meta = self._load_meta()
            if meta and meta.get("total") != total:
                # 文件大小变化（换源/内容更新）：丢弃旧进度重新下载
                self._clear_parts()
                meta = None
            thread_count = (meta.get("threads") if meta else None) \
                or min(self.threads, total)
            thread_count = max(1, min(int(thread_count), 16))
            self._save_meta(thread_count, total)

            self._baseline_bytes = self._existing_part_bytes(thread_count)
            self._emit_status(
                f"开始下载：{thread_count} 线程，总大小 {self._fmt(total)}，"
                f"已续传 {self._fmt(self._baseline_bytes)}")

            ranges = self._split_ranges(total, thread_count)
            workers = []
            for i, (start, end) in enumerate(ranges):
                workers.append(threading.Thread(
                    target=self._worker, args=(i, start, end), daemon=True))
            # 若在获取信息期间被暂停，工作线程启动后会阻塞等待
            self._state = "paused" if not self._pause_event.is_set() else "running"
            for t in workers:
                t.start()
            for t in workers:
                t.join()

            if self._stop_event.is_set():
                self._state = "stopped"
                self._emit_status("下载已停止")
                return
            if self._all_parts_complete(total, thread_count):
                self._finalize(total, thread_count)
                self._state = "finished"
                self._emit_status(f"下载完成：{self.save_path}")
                self._emit_progress(total, total)
            else:
                self._state = "error"
                self._emit_status("下载未完成：部分分块下载失败")
        except Exception as exc:
            self._state = "error"
            self._emit_status(f"下载失败：{exc}")

    def _fetch_total_size(self):
        """获取文件总大小与是否支持断点续传，返回 (total, supports_range)。"""
        # 1) HEAD 请求
        try:
            resp = self.session.head(self.url, allow_redirects=True, timeout=15)
            length = resp.headers.get("Content-Length")
            if length and resp.headers.get("Accept-Ranges", "").lower() == "bytes":
                return int(length), True
        except Exception:
            pass
        # 2) GET + Range: bytes=0-0，从 Content-Range 读取总大小
        try:
            resp = self.session.get(self.url, headers={"Range": "bytes=0-0"},
                                    stream=True, timeout=15)
            try:
                if resp.status_code == 206:
                    content_range = resp.headers.get("Content-Range", "")
                    # 形如 bytes 0-0/123456
                    total = int(content_range.rsplit("/", 1)[-1])
                    return total, True
                length = resp.headers.get("Content-Length")
                if length:
                    return int(length), False  # 知道大小但不支持分块
            finally:
                resp.close()
        except Exception:
            pass
        return None, False

    def _worker(self, index, start_byte, end_byte):
        """单个分块的工作线程：断点续传、暂停/恢复、限速。"""
        part_path = self._part_path(index)
        rate_state = {"tokens": 0.0, "last": time.time()}
        try:
            # 断点续传：从已有 part 文件大小处继续
            offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            position = start_byte + offset
            if position >= end_byte:
                return  # 该分块此前已下载完成
            headers = {"Range": f"bytes={position}-{end_byte - 1}"}
            resp = self.session.get(self.url, headers=headers, stream=True, timeout=30)
            try:
                resp.raise_for_status()
                if resp.status_code != 206:
                    raise RuntimeError("服务器未返回 206，可能不支持多线程分块")
                with open(part_path, "ab") as f:
                    for chunk in resp.iter_content(chunk_size=self.CHUNK_SIZE):
                        if self._stop_event.is_set():
                            return
                        if not self._wait_if_paused():
                            return
                        f.write(chunk)
                        self._on_bytes(len(chunk))
                        self._throttle(len(chunk), rate_state)
            finally:
                resp.close()
        except Exception as exc:
            self._stop_event.set()
            self._emit_status(f"分块 {index} 出错：{exc}")

    def _single_stream_download(self, total):
        """服务器不支持 Range 时降级为单线程流式下载（.part → 改名）。"""
        part_path = f"{self.save_path}.part"
        rate_state = {"tokens": 0.0, "last": time.time()}
        try:
            existing = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            headers = {"Range": f"bytes={existing}-"} if existing else {}
            resp = self.session.get(self.url, headers=headers, stream=True, timeout=30)
            try:
                resp.raise_for_status()
                if resp.status_code == 200 and headers:
                    # 服务器忽略 Range：从头开始，覆盖旧 part
                    existing = 0
                    mode = "wb"
                else:
                    mode = "ab"
                self._baseline_bytes = existing
                if total is None:
                    length = resp.headers.get("Content-Length")
                    if length:
                        total = int(length) + existing
                        self.total_size = total
                self._state = "paused" if not self._pause_event.is_set() else "running"
                self._emit_status(
                    f"单线程下载开始，总大小 {self._fmt(total) if total else '未知'}")
                with open(part_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=self.CHUNK_SIZE):
                        if self._stop_event.is_set():
                            return
                        if not self._wait_if_paused():
                            return
                        f.write(chunk)
                        self._on_bytes(len(chunk))
                        self._throttle(len(chunk), rate_state)
            finally:
                resp.close()

            if self._stop_event.is_set():
                self._state = "stopped"
                self._emit_status("下载已停止")
                return
            # 流正常结束 = 下载完成：part 改名为正式文件
            if os.path.exists(self.save_path):
                os.remove(self.save_path)
            os.rename(part_path, self.save_path)
            self._state = "finished"
            self.total_size = total
            self._emit_status(f"下载完成：{self.save_path}")
            self._emit_progress(self.total_size or 0, self.total_size or 0)
        except Exception as exc:
            self._state = "error"
            self._emit_status(f"下载失败：{exc}")

    # ------------------------------------------------------------------
    # 断点续传辅助：part / meta 文件
    # ------------------------------------------------------------------
    def _part_path(self, index):
        return f"{self.save_path}.part.{index}"

    def _meta_path(self):
        return f"{self.save_path}.part.meta"

    def _save_meta(self, thread_count, total):
        """记录线程数与总大小，保证跨实例续传时范围一致。"""
        try:
            with open(self._meta_path(), "w", encoding="utf-8") as f:
                json.dump({"threads": thread_count, "total": total}, f)
        except OSError:
            pass  # 元信息写失败不影响本次下载

    def _load_meta(self):
        try:
            with open(self._meta_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _existing_part_bytes(self, thread_count):
        """统计已有 part 文件占用的字节数（用于续传进度与完整性判断）。"""
        total = 0
        for i in range(thread_count):
            part = self._part_path(i)
            try:
                total += os.path.getsize(part)
            except OSError:
                pass
        return total

    def _all_parts_complete(self, total, thread_count):
        return self._existing_part_bytes(thread_count) >= total

    def _split_ranges(self, total, count):
        """把 [0, total) 均分为 count 段，返回 [(start, end), ...]。"""
        chunk = total // count
        ranges = []
        for i in range(count):
            start = i * chunk
            end = total if i == count - 1 else start + chunk
            ranges.append((start, end))
        return ranges

    def _finalize(self, total, thread_count):
        """按顺序合并所有分块为最终文件，并删除 .part / .meta。"""
        with open(self.save_path, "wb") as out:
            for i in range(thread_count):
                part = self._part_path(i)
                if not os.path.exists(part):
                    continue
                with open(part, "rb") as pf:
                    shutil.copyfileobj(pf, out)
                os.remove(part)
        try:
            os.remove(self._meta_path())
        except OSError:
            pass

    def _clear_parts(self):
        """删除全部 part 与 meta（文件大小变化时丢弃旧进度）。"""
        for name in os.listdir(os.path.dirname(self.save_path) or "."):
            if name.startswith(os.path.basename(self.save_path) + ".part"):
                try:
                    os.remove(os.path.join(os.path.dirname(self.save_path) or ".", name))
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 回调 / 限速 / 暂停等待
    # ------------------------------------------------------------------
    def _emit_status(self, msg):
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass

    def _emit_progress(self, current, total):
        if self.on_progress:
            try:
                self.on_progress(current, total)
            except Exception:
                pass

    def _on_bytes(self, n):
        """累计已下载字节数，并节流触发进度回调。"""
        now = time.time()
        with self._lock:
            self._completed_bytes += n
            should_report = now - self._last_report >= self.REPORT_INTERVAL
            if should_report:
                self._last_report = now
                current = self._baseline_bytes + self._completed_bytes
                total = self.total_size or 0
        if should_report:
            self._emit_progress(current, total)

    def _throttle(self, n, state):
        """令牌桶限速。state 为线程本地的 {'tokens': float, 'last': time}。"""
        if self._bytes_per_sec <= 0:
            return
        rate = self._bytes_per_sec / self.threads  # 每线程速率（字节/秒）
        now = time.time()
        state["tokens"] += (now - state["last"]) * rate
        state["last"] = now
        if state["tokens"] > rate:
            state["tokens"] = rate  # 令牌上限 = 1 秒额度，允许小幅突发
        state["tokens"] -= n
        if state["tokens"] < 0:
            time.sleep(-state["tokens"] / rate)
            state["tokens"] = 0
            state["last"] = time.time()

    def _wait_if_paused(self):
        """暂停时阻塞；返回 False 表示应退出（收到停止信号）。"""
        while not self._pause_event.is_set():
            if self._stop_event.is_set():
                return False
            self._pause_event.wait(0.2)
        return not self._stop_event.is_set()

    @staticmethod
    def _fmt(num):
        """把字节数格式化为可读字符串。"""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if num < 1024 or unit == "TB":
                return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
            num /= 1024


if __name__ == "__main__":
    # 便于单独测试：python downloader.py <url> <保存路径> [线程数] [限速MB/s]
    import sys
    if len(sys.argv) < 3:
        print("用法：python downloader.py <url> <保存路径> [线程数] [限速MB/s]")
        sys.exit(1)
    url = sys.argv[1]
    path = sys.argv[2]
    threads = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    limit = float(sys.argv[4]) if len(sys.argv) > 4 else None

    def on_progress(current, total):
        pct = current / total * 100 if total else 0
        print(f"\r进度：{Downloader._fmt(current)} / {Downloader._fmt(total)}（{pct:.1f}%）", end="")

    dl = Downloader(url, path, threads=threads, speed_limit=limit,
                    on_progress=on_progress, on_status=lambda m: print(f"\n[{m}]"))
    dl.start()
    while dl.is_busy():
        time.sleep(0.1)
    print(f"\n结束状态：{dl.state}")
