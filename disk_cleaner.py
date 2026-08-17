# -*- coding: utf-8 -*-
"""
disk_cleaner.py —— 磁盘垃圾清理模块

提供：
    - DiskCleaner 类：scan() 扫描垃圾位置，返回 (file_list, total_size)
    - clean(files) 函数：把文件/目录列表移动到回收站（依赖 send2trash）

扫描范围（覆盖 C 盘常见垃圾位置；D 盘存在常见临时目录时也会扫描）：
    1. 系统临时目录：%WINDIR%\\Temp（通常即 C:\\Windows\\Temp）
    2. 用户临时目录：%TEMP%
    3. Chrome / Edge 浏览器缓存（Default 配置下的 Cache、Code Cache、
       GPUCache、Service Worker 缓存等）
    4. 系统目录下的 *.log 日志文件（仅 %WINDIR% 递归范围内）

说明：
    - 回收站暂不处理：清空回收站属于“深度清理”，操作不可逆且需要特殊
      权限，为避免误删用户文件，本版本不包含，后续可扩展。
    - 浏览器缓存按“整个缓存目录”作为一个清理项：缓存内可能有数万个
      小文件，逐个移动极慢，整目录移入回收站效率更高、效果相同。
    - 扫描在调用线程中执行（GUI 中应放入后台线程），可通过
      progress_callback 回调实时反馈进度。
"""
import os

# 默认浏览器缓存子目录（相对各浏览器的 User Data 目录）
_BROWSER_CACHE_SUBDIRS = [
    r"Default\Cache",
    r"Default\Code Cache",
    r"Default\GPUCache",
    r"Default\Service Worker\CacheStorage",
    r"Default\Service Worker\ScriptCache",
]

# 浏览器列表：(User Data 目录相对路径, 显示名)
_BROWSERS = [
    (r"Google\Chrome\User Data", "Chrome"),
    (r"Microsoft\Edge\User Data", "Edge"),
]

# D 盘常见临时目录（存在才扫描；不存在会自动跳过）
_EXTRA_TEMP_DIRS = [r"D:\Temp", r"D:\Windows\Temp"]


def _format_size(num: int) -> str:
    """把字节数格式化为可读字符串（B/KB/MB/GB/TB）。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024


class DiskCleaner:
    """磁盘垃圾扫描器。"""

    def __init__(self, progress_callback=None):
        """
        :param progress_callback: 可选进度回调，签名：
                callback(count, total_size, message)
            count 为已发现项数，total_size 为已发现总字节数（实时累计），
            message 为当前处理的文件/目录或阶段提示。
            注意：回调在扫描线程中执行；若用于刷新 Tk 界面，
            应通过“队列 + after() 轮询”转发到主线程。
        """
        self._progress_callback = progress_callback

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _report(self, count: int, total_size: int, message: str):
        """触发进度回调；回调自身出错不影响扫描。"""
        if self._progress_callback:
            try:
                self._progress_callback(count, total_size, message)
            except Exception:
                pass

    def _collect_files(self, root_dir, file_list, base_size, pattern=None):
        """递归收集目录内符合条件的文件，就地追加到 file_list。

        :param root_dir:  待扫描的根目录
        :param file_list: 文件路径列表（就地追加）
        :param base_size: 扫描本目录前已累计的大小（用于进度显示）
        :param pattern:   扩展名过滤（如 ".log"），None 表示全部文件
        :return: (新增数量, 新增大小)
        """
        if not os.path.isdir(root_dir):
            return 0, 0

        added_count = 0
        added_size = 0
        for dirpath, dirnames, filenames in os.walk(root_dir, onerror=lambda err: None):
            # 跳过符号链接/联接点（junction），防止目录循环
            dirnames[:] = [d for d in dirnames
                           if not os.path.islink(os.path.join(dirpath, d))]
            for name in filenames:
                if pattern and not name.lower().endswith(pattern):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    fsize = os.path.getsize(full)
                except OSError:
                    continue  # 无权限等，跳过该文件
                file_list.append(full)
                added_count += 1
                added_size += fsize
                # 实时上报进度（base_size + added_size 即当前累计总大小）
                self._report(len(file_list), base_size + added_size, full)
        return added_count, added_size

    def _dir_size(self, path: str) -> int:
        """计算目录总大小（字节）。"""
        total = 0
        for dirpath, dirnames, filenames in os.walk(path, onerror=lambda err: None):
            dirnames[:] = [d for d in dirnames
                           if not os.path.islink(os.path.join(dirpath, d))]
            for name in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
        return total

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def scan(self):
        """扫描所有垃圾位置。

        :return: (file_list, total_size)
                 file_list —— 待清理的文件/目录路径列表；
                 total_size —— 总大小（字节）。
        """
        file_list = []
        total_size = 0

        # 1) 系统临时目录 %WINDIR%\Temp（通常为 C:\Windows\Temp）
        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        system_temp = os.path.join(win_dir, "Temp")
        self._report(len(file_list), total_size,
                     f"== 扫描系统临时目录：{system_temp} ==")
        _, added_size = self._collect_files(system_temp, file_list, total_size)
        total_size += added_size

        # 2) 用户临时目录 %TEMP%
        temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
        if temp_dir and os.path.isdir(temp_dir):
            self._report(len(file_list), total_size,
                         f"== 扫描用户临时目录：{temp_dir} ==")
            _, added_size = self._collect_files(temp_dir, file_list, total_size)
            total_size += added_size

        # 3) Chrome / Edge 浏览器缓存
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        for browser_rel, browser_name in _BROWSERS:
            user_data = os.path.join(local_appdata, browser_rel)
            for sub in _BROWSER_CACHE_SUBDIRS:
                cache_dir = os.path.join(user_data, sub)
                if os.path.isdir(cache_dir):
                    self._report(len(file_list), total_size,
                                 f"== {browser_name} 缓存：{cache_dir} ==")
                    # 缓存内小文件数以万计，整个目录作为一个清理项
                    cache_size = self._dir_size(cache_dir)
                    file_list.append(cache_dir)
                    total_size += cache_size
                    self._report(len(file_list), total_size,
                                 f"  缓存目录合计 {_format_size(cache_size)}")

        # 4) 系统目录下的 *.log 日志文件（仅 %WINDIR% 递归范围内）
        self._report(len(file_list), total_size,
                     f"== 扫描系统日志文件（{win_dir} 下 *.log）==")
        _, added_size = self._collect_files(win_dir, file_list, total_size,
                                            pattern=".log")
        total_size += added_size

        # 5) D 盘常见临时目录（存在才扫描，不存在自动跳过）
        for extra in _EXTRA_TEMP_DIRS:
            if os.path.isdir(extra):
                self._report(len(file_list), total_size,
                             f"== 扫描 D 盘临时目录：{extra} ==")
                _, added_size = self._collect_files(extra, file_list, total_size)
                total_size += added_size

        # 扫描结束汇总
        self._report(len(file_list), total_size,
                     f"== 扫描结束：共 {len(file_list)} 项，"
                     f"合计 {_format_size(total_size)} ==")
        return file_list, total_size


def clean(files):
    """把文件/目录列表移动到回收站（不是永久删除）。

    :param files: 文件或目录路径列表
    :return: (成功数量, 失败数量)
    :raises RuntimeError: 未安装 send2trash 时抛出，提示先安装
    """
    # 延迟导入：未安装时给出明确提示，而不是直接报 ImportError
    try:
        import send2trash
    except ImportError:
        raise RuntimeError(
            "未安装 send2trash，无法将文件移动到回收站。\n"
            "请先执行：pip install send2trash"
        )

    moved = 0
    failed = 0
    for path in files:
        try:
            if os.path.exists(path):
                send2trash.send2trash(path)  # 移动到回收站
                moved += 1
        except Exception:
            failed += 1  # 文件被占用 / 无权限等，跳过并计数
    return moved, failed


if __name__ == "__main__":
    # 便于单独测试：python disk_cleaner.py（只扫描不删除）
    print("开始扫描（仅统计，不删除任何文件）……")
    cleaner = DiskCleaner()
    files, total = cleaner.scan()
    print(f"扫描完成：{len(files)} 项，合计 {_format_size(total)}")
