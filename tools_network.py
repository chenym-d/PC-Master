# -*- coding: utf-8 -*-
"""
tools_network.py —— 网络工具集（5 个工具）

每个工具是一个函数，签名统一为 func(parent)（与 tools_system 相同）：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

工具列表：
    1. speed_test(parent)    网速测试（基于 speedtest-cli，需 pip install speedtest-cli）
    2. ip_query(parent)      显示内网 / 外网 IP
    3. ping_tool(parent)     图形化 Ping（连续/单次，可停止）
    4. port_scanner(parent)  端口扫描（TCP 连接测试）
    5. wifi_password(parent) 查看已连接 Wi-Fi 的密码（netsh wlan，仅限本机）

依赖说明：
    - speedtest-cli 可选：未安装时网速测试会提示安装命令；
    - 本工具复用 tools_system 的窗口/线程辅助函数。
"""
import queue
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from tools_system import _open_tool_window, _run_in_thread

# 外网 IP 查询接口（依次尝试）
_EXTERNAL_IP_APIS = [
    "https://api.ipify.org",
    "https://myip.ipip.net",
]

# 界面配色（与 tools_system 保持一致）
_BG = "#f5f6fa"
_TITLE_FG = "#1f2a3a"
_HINT_FG = "#7a8699"
_BTN_BG = "#3d5a80"
_BTN_FG = "#ffffff"


# ----------------------------------------------------------------------
# 1. 网速测试（speedtest-cli）
# ----------------------------------------------------------------------
def _pick_cn_server(st):
    """优先在国内节点中选延迟最低的服务器（国内网络下避免选到海外节点）。"""
    try:
        st.get_servers()  # 获取服务器列表（不做延迟测试）
        cn_ids = [s["id"] for group in st.servers.values()
                  for s in group if s.get("country") == "CN"]
        if cn_ids:
            # 只对国内节点测延迟，取前 15 个候选避免耗时过长
            st.get_best_server(servers=cn_ids[:15])
            return True
    except Exception:
        pass
    return False


def _run_speedtest():
    """执行 speedtest-cli 测速，返回 (ping_ms, download_mbps, upload_mbps)。

    ping_ms 在无法测得有效延迟时为 -1（界面显示“超时”）。
    策略：优先 HTTPS + 国内节点；ping 异常时回退非安全模式全量选择。
    """
    try:
        import speedtest
    except ImportError:
        raise RuntimeError(
            "未安装 speedtest-cli，无法测速。\n请先执行：pip install speedtest-cli")

    st = speedtest.Speedtest(timeout=10, secure=True)
    if not _pick_cn_server(st):
        try:
            st.get_best_server()
        except Exception:
            pass
    ping = st.results.ping if st.results.server else None
    if ping is None or ping > 10000:
        # 回退：非安全模式 + 全量自动选择（兼容部分网络环境）
        try:
            st2 = speedtest.Speedtest(timeout=10, secure=False)
            st2.get_best_server()
            if st2.results.server and st2.results.ping and st2.results.ping <= 10000:
                st = st2
        except Exception:
            pass

    ping = st.results.ping if st.results.server and st.results.ping and st.results.ping <= 10000 else -1
    download_bps = st.download()  # 下载（bit/s）
    upload_bps = st.upload()      # 上传（bit/s）
    return ping, download_bps / 1e6, upload_bps / 1e6


# 简易下载测速使用的国内镜像文件（阿里云 PyPI 列表页，体积稳定且可达）
_HTTP_TEST_URL = "https://mirrors.aliyun.com/pypi/simple/pillow/"


def _http_download_speed(url=_HTTP_TEST_URL, duration=6):
    """简易下载测速：从国内镜像连续下载指定时长，返回平均 MB/s。

    不依赖 speedtest.net 节点，在国内网络下更可靠（仅测下载）。
    """
    import requests as _rq
    import time as _t
    start = _t.time()
    total = 0
    with _rq.get(url, stream=True, timeout=15) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            total += len(chunk)
            if _t.time() - start >= duration:
                break
    elapsed = _t.time() - start
    return total / 1048576 / elapsed if elapsed > 0 else 0.0


def speed_test(parent):
    """网速测试工具。"""
    win = _open_tool_window(parent, "网速测试", 480, 410)
    win.resizable(False, False)

    status_var = tk.StringVar(value="就绪")
    ping_var = tk.StringVar(value="--")
    download_var = tk.StringVar(value="--")
    upload_var = tk.StringVar(value="--")

    tk.Label(win, text="网速测试", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(16, 2))
    tk.Label(win, text="基于 speedtest-cli，测速可能需要 30~60 秒",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 10))

    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(pady=(0, 10))
    btn = tk.Button(btn_row, text="开始测速", command=lambda: start(),
                    font=("Microsoft YaHei UI", 12), bg=_BTN_BG, fg=_BTN_FG,
                    relief="flat", padx=16, pady=6, cursor="hand2")
    btn.pack(side="left")
    btn_simple = tk.Button(btn_row, text="简易下载测速", command=lambda: start_simple(),
                           font=("Microsoft YaHei UI", 12), bg="#e67e22", fg="#ffffff",
                           relief="flat", padx=16, pady=6, cursor="hand2")
    btn_simple.pack(side="left", padx=(10, 0))

    result = tk.Frame(win, bg="#ffffff", relief="solid", bd=1)
    result.pack(fill="x", padx=20, pady=(0, 8))
    for text, var, color in (("Ping", ping_var, "#2980b9"),
                             ("下载", download_var, "#27ae60"),
                             ("上传", upload_var, "#e67e22")):
        cell = tk.Frame(result, bg="#ffffff")
        cell.pack(side="left", expand=True, pady=10)
        tk.Label(cell, text=text, font=("Microsoft YaHei UI", 10),
                 bg="#ffffff", fg="#7a8699").pack()
        tk.Label(cell, textvariable=var, font=("Microsoft YaHei UI", 13, "bold"),
                 bg="#ffffff", fg=color).pack()

    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(pady=(0, 10))

    def start():
        btn.config(state="disabled")
        status_var.set("正在初始化……")
        _run_in_thread(win, _run_speedtest, on_done)

    def on_done(kind, payload):
        btn.config(state="normal")
        if kind == "error":
            status_var.set(f"测速失败：{payload}")
            return
        ping, download, upload = payload
        ping_var.set(f"{ping:.0f} ms" if ping and ping > 0 else "超时")
        download_var.set(f"{download:.1f} Mbps")
        upload_var.set(f"{upload:.1f} Mbps")
        status_var.set("测速完成")

    def start_simple():
        """简易下载测速（国内镜像），不依赖 speedtest.net 节点。"""
        btn_simple.config(state="disabled")
        status_var.set("简易测速中（下载国内镜像约 6 秒）……")
        ping_var.set("--")
        upload_var.set("--")
        _run_in_thread(win, _http_download_speed, on_simple_done)

    def on_simple_done(kind, payload):
        btn_simple.config(state="normal")
        if kind == "error":
            status_var.set(f"简易测速失败：{payload}")
            return
        download_var.set(f"{payload:.1f} Mbps")
        status_var.set("简易测速完成（仅下载；上传需 speedtest-cli）")


# ----------------------------------------------------------------------
# 2. IP 查询
# ----------------------------------------------------------------------
def _get_local_ips():
    """获取本机内网 IPv4 地址列表。"""
    ips = set()
    # 技巧：UDP connect 不实际发包，仅探测出口网卡 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    # 通过主机名解析补充
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ips)


# 匹配 IPv4 地址（用于从接口返回文本中提取纯 IP）
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def _get_external_ip():
    """查询外网 IP（返回纯 IP 地址，避免长文本把界面撑满）；失败返回错误提示。"""
    try:
        import requests
    except ImportError:
        return "获取失败（未安装 requests）"
    for api in _EXTERNAL_IP_APIS:
        try:
            resp = requests.get(api, timeout=10)
            if resp.status_code == 200:
                text = resp.text.strip()
                match = _IPV4_RE.search(text)
                if match:
                    return match.group(0)  # 只返回纯 IP
                if text:
                    return text
        except Exception:
            continue
    return "获取失败（请检查网络连接）"


def ip_query(parent):
    """内网 / 外网 IP 查询工具。"""
    win = _open_tool_window(parent, "IP 查询", 520, 320)
    win.resizable(False, False)

    hostname_var = tk.StringVar(value="--")
    local_var = tk.StringVar(value="--")
    external_var = tk.StringVar(value="--")

    form = tk.Frame(win, bg="#f5f6fa")
    form.pack(fill="x", padx=20, pady=(16, 8))
    rows = [("主机名", hostname_var), ("内网 IP", local_var), ("外网 IP", external_var)]
    for i, (label, var) in enumerate(rows):
        tk.Label(form, text=f"{label}：", font=("Microsoft YaHei UI", 11),
                 bg="#f5f6fa", fg="#1f2a3a").grid(row=i, column=0, sticky="w", pady=4)
        tk.Label(form, textvariable=var, font=("Consolas", 11), bg="#ffffff",
                 fg="#22303f", anchor="w", relief="solid", bd=1,
                 padx=6, wraplength=300).grid(row=i, column=1, sticky="ew", pady=4, padx=(0, 8))
    form.columnconfigure(1, weight=1)

    tk.Button(win, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 11), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=20, pady=4, cursor="hand2").pack(pady=(4, 8))
    tk.Label(win, text="外网 IP 通过公网接口查询，需要网络连接",
             font=("Microsoft YaHei UI", 9), bg="#f5f6fa", fg="#7a8699").pack(pady=(0, 10))

    def refresh():
        hostname_var.set(socket.gethostname())
        local_ips = _get_local_ips()
        local_var.set("、".join(local_ips) if local_ips else "获取失败")
        external_var.set("查询中……")
        _run_in_thread(win, _get_external_ip, on_external)

    def on_external(kind, payload):
        if kind == "error":
            external_var.set(f"查询失败：{payload}")
        else:
            external_var.set(payload)

    refresh()


# ----------------------------------------------------------------------
# 3. 图形化 Ping
# ----------------------------------------------------------------------
def _run_ping(host, count=1, timeout_ms=3000):
    """执行一次 ping，返回精简后的结果文本。"""
    try:
        proc = subprocess.run(
            ["ping", "-n", str(count), "-w", str(timeout_ms), host],
            capture_output=True, text=True, timeout=timeout_ms / 1000 + 5)
        output = (proc.stdout + proc.stderr).strip()
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        if not lines:
            return "(无输出)"
        # 优先取统计行（中文“平均”/“丢失”，英文 Average/Minimum/Lost）
        for line in reversed(lines):
            if any(k in line for k in ("平均", "Average", "最短", "Minimum",
                                       "丢失", "Lost", "时间", "time")):
                return line
        return lines[-1]
    except subprocess.TimeoutExpired:
        return "ping 超时"
    except Exception as exc:
        return f"ping 执行失败：{exc}"


def ping_tool(parent):
    """图形化 Ping 工具（支持连续 / 单次，可停止）。"""
    win = _open_tool_window(parent, "Ping 测试", 560, 480)

    host_var = tk.StringVar(value="127.0.0.1")
    interval_var = tk.StringVar(value="2")
    continuous_var = tk.BooleanVar(value=True)

    form = tk.Frame(win, bg="#f5f6fa")
    form.pack(fill="x", padx=14, pady=(12, 6))
    tk.Label(form, text="目标：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(form, textvariable=host_var, font=("Consolas", 10), width=22).pack(side="left")
    tk.Label(form, text="   间隔(秒)：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(form, textvariable=interval_var, font=("Consolas", 10), width=5).pack(side="left")
    tk.Checkbutton(form, text="连续 Ping", variable=continuous_var,
                   bg="#f5f6fa", font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(8, 0))

    btn_row = tk.Frame(win, bg="#f5f6fa")
    btn_row.pack(fill="x", padx=14, pady=(0, 6))
    start_btn = tk.Button(btn_row, text="开始", command=lambda: start(),
                          font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                          relief="flat", padx=14, cursor="hand2")
    start_btn.pack(side="left")
    stop_btn = tk.Button(btn_row, text="停止", command=lambda: stop(),
                         font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
                         relief="flat", padx=14, state="disabled", cursor="hand2")
    stop_btn.pack(side="left", padx=(8, 0))

    log = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="none",
                  bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=log.yview)
    log.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 14), pady=(0, 10))
    log.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 10))

    q = queue.Queue()
    stop_event = threading.Event()
    running = [False]  # 用列表让闭包可以修改

    def append_line(message):
        log.configure(state="normal")
        log.insert("end", message + "\n")
        log.see("end")
        log.configure(state="disabled")

    def start():
        if running[0]:
            return
        # 在主线程读取界面参数（Tk 变量不可在工作线程访问）
        host = host_var.get().strip() or "127.0.0.1"
        try:
            interval = max(0.5, float(interval_var.get() or 2))
        except ValueError:
            interval = 2.0
        continuous = continuous_var.get()
        stop_event.clear()
        running[0] = True
        start_btn.config(state="disabled")
        stop_btn.config(state="normal")
        threading.Thread(target=worker, args=(host, interval, continuous),
                         daemon=True).start()
        win.after(200, poll)

    def worker(host, interval, continuous):
        while not stop_event.is_set():
            result = _run_ping(host)
            q.put((time.strftime("%H:%M:%S"), host, result))
            if not continuous:
                break
            stop_event.wait(interval)  # 等待期间可被 stop() 唤醒
        q.put(None)

    def poll():
        try:
            while True:
                item = q.get_nowait()
                if item is None:
                    running[0] = False
                    start_btn.config(state="normal")
                    stop_btn.config(state="disabled")
                    return
                ts, host, result = item
                append_line(f"[{ts}] {host} → {result}")
        except queue.Empty:
            pass
        win.after(200, poll)

    def stop():
        stop_event.set()


# ----------------------------------------------------------------------
# 4. 端口扫描
# ----------------------------------------------------------------------
def _check_port(host, port, timeout=0.3):
    """尝试 TCP 连接指定端口；开放返回 True。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def port_scanner(parent):
    """端口扫描工具（TCP 连接测试）。"""
    win = _open_tool_window(parent, "端口扫描", 480, 460)

    host_var = tk.StringVar(value="127.0.0.1")
    start_var = tk.StringVar(value="1")
    end_var = tk.StringVar(value="100")
    progress_var = tk.StringVar(value="就绪")

    form = tk.Frame(win, bg="#f5f6fa")
    form.pack(fill="x", padx=14, pady=(12, 6))
    tk.Label(form, text="目标：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(form, textvariable=host_var, font=("Consolas", 10), width=18).pack(side="left")
    tk.Label(form, text="   端口：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(form, textvariable=start_var, font=("Consolas", 10), width=5).pack(side="left")
    tk.Label(form, text="—", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(form, textvariable=end_var, font=("Consolas", 10), width=5).pack(side="left")

    btn = tk.Button(win, text="开始扫描", command=lambda: start(),
                    font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                    relief="flat", padx=14, cursor="hand2")
    btn.pack(anchor="w", padx=14, pady=(0, 6))

    listbox = tk.Listbox(win, font=("Consolas", 10), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 14), pady=(0, 8))
    listbox.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 8))

    tk.Label(win, textvariable=progress_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#1f2a3a", anchor="w").pack(fill="x", padx=14, pady=(0, 2))
    tk.Label(win, text="提示：超时 0.3 秒/端口，扫描范围越大耗时越长；对丢弃数据包的主机更慢",
             font=("Microsoft YaHei UI", 9), bg="#f5f6fa", fg="#7a8699",
             anchor="w").pack(fill="x", padx=14, pady=(0, 8))

    q = queue.Queue()
    stop_event = threading.Event()
    running = [False]

    def start():
        if running[0]:
            return
        host = host_var.get().strip()
        try:
            start_port = int(start_var.get())
            end_port = int(end_var.get())
            if not (1 <= start_port <= end_port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("端口扫描", "请输入有效的端口范围（1~65535）。")
            return
        listbox.delete(0, "end")
        progress_var.set("正在解析主机……")
        running[0] = True
        btn.config(state="disabled")
        threading.Thread(target=worker, args=(host, start_port, end_port), daemon=True).start()
        win.after(150, poll)

    def worker(host, start_port, end_port):
        try:
            socket.gethostbyname(host)  # 验证主机可解析
        except OSError:
            q.put(("done", f"无法解析主机：{host}"))
            return
        total = end_port - start_port + 1
        open_ports = []
        for i, port in enumerate(range(start_port, end_port + 1)):
            if stop_event.is_set():
                q.put(("done", f"已停止（发现 {len(open_ports)} 个开放端口）"))
                return
            if _check_port(host, port):
                open_ports.append(port)
                q.put(("open", port))
            scanned = i + 1
            if scanned % 20 == 0 or scanned == total:
                q.put(("progress", (scanned, total)))
        q.put(("done", f"扫描完成：共发现 {len(open_ports)} 个开放端口"))

    def poll():
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "open":
                    listbox.insert("end", f"  {host_var.get().strip()} : {payload}  （开放）")
                elif kind == "progress":
                    scanned, total = payload
                    progress_var.set(f"已扫描 {scanned}/{total} 端口……")
                elif kind == "done":
                    running[0] = False
                    btn.config(state="normal")
                    progress_var.set(payload)
                    return
        except queue.Empty:
            pass
        win.after(150, poll)

    def stop():
        stop_event.set()


# ----------------------------------------------------------------------
# 5. Wi-Fi 密码查看（netsh）
# ----------------------------------------------------------------------
def _get_wifi_profiles():
    """列出本机所有 Wi-Fi 配置文件名称。"""
    try:
        proc = subprocess.run(["netsh", "wlan", "show", "profiles"],
                              capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return [], f"执行 netsh 失败：{exc}"
    profiles = []
    for line in proc.stdout.splitlines():
        if (("配置文件" in line or "profile" in line.lower()) and ":" in line):
            name = line.split(":", 1)[1].strip()
            if name:
                profiles.append(name)
    if not profiles:
        return [], "未找到 Wi-Fi 配置文件（可能没有无线网卡或服务未启动）"
    return profiles, ""


def _get_wifi_password(profile):
    """查询指定 Wi-Fi 配置文件的密码（key=clear）。"""
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "profile", f'name="{profile}"', "key=clear"],
            capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return f"（获取失败：{exc}）"
    for line in proc.stdout.splitlines():
        if "关键内容" in line or "Key Content" in line:
            return line.split(":", 1)[1].strip()
    return "（无密码或无法读取，需已连接过且具有管理员权限）"


def wifi_password(parent):
    """查看已连接 Wi-Fi 密码工具。"""
    win = _open_tool_window(parent, "Wi-Fi 密码查看", 520, 440)

    listbox = tk.Listbox(win, font=("Consolas", 10), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 14), pady=(12, 6))
    listbox.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(12, 6))

    btn_row = tk.Frame(win, bg="#f5f6fa")
    btn_row.pack(fill="x", padx=14, pady=(0, 4))
    tk.Button(btn_row, text="刷新列表", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="查看密码", command=lambda: show_password(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))

    pwd_var = tk.StringVar(value="请选择上方配置文件后点击“查看密码”")
    tk.Label(win, textvariable=pwd_var, font=("Consolas", 11), bg="#ffffff",
             fg="#22303f", anchor="w", relief="solid", bd=1,
             padx=8).pack(fill="x", padx=14, pady=(6, 4))
    tk.Label(win, text="提示：需要无线网卡且目标网络曾被本机连接过；部分密码读取需要管理员权限",
             font=("Microsoft YaHei UI", 9), bg="#f5f6fa", fg="#7a8699",
             anchor="w").pack(fill="x", padx=14, pady=(0, 10))

    profiles = []

    def refresh():
        listbox.delete(0, "end")
        pwd_var.set("正在读取配置文件……")
        _run_in_thread(win, _get_wifi_profiles, on_profiles)

    def on_profiles(kind, payload):
        if kind == "error":
            pwd_var.set(f"读取失败：{payload}")
            return
        items, message = payload
        profiles.clear()
        for name in items:
            profiles.append(name)
            listbox.insert("end", name)
        pwd_var.set(message if message else f"共 {len(items)} 个配置文件")

    def show_password():
        sel = listbox.curselection()
        if not sel:
            messagebox.showinfo("Wi-Fi 密码", "请先选择一个 Wi-Fi 配置文件。")
            return
        name = profiles[sel[0]]
        pwd_var.set("正在获取……")
        _run_in_thread(win, lambda: _get_wifi_password(name), on_password)

    def on_password(kind, payload):
        if kind == "error":
            pwd_var.set(f"获取失败：{payload}")
        else:
            pwd_var.set(f"「{profiles[listbox.curselection()[0]] if listbox.curselection() else ''}」密码：{payload}")

    refresh()
