# -*- coding: utf-8 -*-
"""
tools_security.py —— 渗透测试 / 网络安全工具集（10 个工具）

每个工具是一个函数，签名统一为 func(parent)（与 tools_system 相同）：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

工具列表：
    1. port_scan(parent)       端口扫描（并发 TCP 扫描 + 服务识别）
    2. subnet_scan(parent)     局域网主机发现（Ping 网段 + ARP 解析 MAC）
    3. traceroute(parent)      路由追踪（tracert 图形化）
    4. whois_lookup(parent)    WHOIS 查询（RDAP 协议）
    5. dns_lookup(parent)      DNS 解析查询（nslookup）
    6. http_header(parent)     HTTP 安全头检测
    7. password_strength(parent) 密码强度检测
    8. hash_tools(parent)      哈希计算与弱密码字典比对
    9. ip_geo(parent)          IP 归属地查询
   10. net_stat(parent)        网络连接状态（psutil / netstat）

声明：以上工具仅用于授权范围内的安全测试与网络诊断，
请遵守所在地法律法规，未经授权禁止扫描他人系统。
"""
import os
import queue
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:
    requests = None

try:
    import psutil
except ImportError:
    psutil = None

from tools_system import _open_tool_window, _run_in_thread

# 常见端口 -> 服务名（用于端口扫描结果标注）
_COMMON_PORTS = {
    20: "FTP-Data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    67: "DHCP", 68: "DHCP", 80: "HTTP", 110: "POP3", 111: "RPC", 123: "NTP",
    135: "RPC", 137: "NetBIOS", 139: "NetBIOS", 143: "IMAP", 161: "SNMP",
    389: "LDAP", 443: "HTTPS", 445: "SMB", 465: "SMTPS", 514: "Syslog",
    587: "SMTP-Sub", 636: "LDAPS", 993: "IMAPS", 995: "POP3S", 1080: "SOCKS",
    1433: "MSSQL", 1521: "Oracle", 1723: "PPTP", 1900: "UPnP", 2181: "ZooKeeper",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 5900: "VNC", 6379: "Redis",
    7001: "WebLogic", 8000: "HTTP-Alt", 8080: "HTTP-Proxy", 8443: "HTTPS-Alt",
    8888: "HTTP-Alt", 9092: "Kafka", 9200: "Elasticsearch", 11211: "Memcached",
    27017: "MongoDB", 50000: "SAP",
}

# 常用端口组
_COMMON_PORT_GROUPS = [
    (20, 25, "邮件(FTP/SMTP 等)"), (80, 80, "HTTP"), (443, 443, "HTTPS"),
    (135, 139, "NetBIOS"), (445, 445, "SMB"), (1433, 1433, "MSSQL"),
    (3306, 3306, "MySQL"), (3389, 3389, "RDP"), (5432, 5432, "PostgreSQL"),
    (6379, 6379, "Redis"), (8080, 8080, "HTTP-Proxy"), (27017, 27017, "MongoDB"),
]


def _service_name(port):
    """返回端口对应的常见服务名（未知返回空串）。"""
    return _COMMON_PORTS.get(port, "")


# ----------------------------------------------------------------------
# 1. 端口扫描（并发）
# ----------------------------------------------------------------------
def _check_port(host, port, timeout=0.5):
    """尝试 TCP 连接指定端口；开放返回 True。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def port_scan(parent):
    """并发端口扫描工具。"""
    win = _open_tool_window(parent, "端口扫描器", 560, 500)
    host_var = tk.StringVar(value="127.0.0.1")
    start_var = tk.StringVar(value="1")
    end_var = tk.StringVar(value="1024")
    progress_var = tk.StringVar(value="就绪")
    msg_q = queue.Queue()
    stop_event = threading.Event()
    running = [False]

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="目标：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=host_var, font=("Consolas", 10), width=20).pack(side="left")
    tk.Label(top, text="   端口：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=start_var, font=("Consolas", 10), width=6).pack(side="left")
    tk.Label(top, text="—", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=end_var, font=("Consolas", 10), width=6).pack(side="left")

    quick = tk.Frame(win, bg="#f5f6fa")
    quick.pack(fill="x", padx=12, pady=(0, 4))
    for s, e, label in _COMMON_PORT_GROUPS[:6]:
        tk.Button(quick, text=label, command=lambda a=s, b=e: set_range(a, b),
                  font=("Microsoft YaHei UI", 9), bg="#aab4c4", fg="#1f2a3a",
                  relief="flat", padx=6, cursor="hand2").pack(side="left", padx=(0, 4))

    btns = tk.Frame(win, bg="#f5f6fa")
    btns.pack(fill="x", padx=12, pady=(0, 4))
    btn = tk.Button(btns, text="开始扫描", command=lambda: start(),
                    font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                    relief="flat", padx=14, cursor="hand2")
    btn.pack(side="left")
    tk.Button(btns, text="停止", command=lambda: stop_event.set(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(8, 0))

    tree = ttk.Treeview(win, columns=("port", "service", "state"), show="headings")
    tree.heading("port", text="端口")
    tree.heading("service", text="常见服务")
    tree.heading("state", text="状态")
    tree.column("port", width=80, anchor="center")
    tree.column("service", width=180)
    tree.column("state", width=120, anchor="center")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))

    tk.Label(win, textvariable=progress_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#1f2a3a", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def set_range(s, e):
        start_var.set(str(s))
        end_var.set(str(e))

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
        for item in tree.get_children():
            tree.delete(item)
        progress_var.set("正在扫描……")
        running[0] = True
        btn.config(state="disabled")
        stop_event.clear()
        threading.Thread(target=worker, args=(host, start_port, end_port), daemon=True).start()
        win.after(150, poll)

    def worker(host, start_port, end_port):
        try:
            socket.gethostbyname(host)
        except OSError:
            msg_q.put(("done", f"无法解析主机：{host}"))
            return
        ports = list(range(start_port, end_port + 1))
        total = len(ports)
        found = 0
        with ThreadPoolExecutor(max_workers=80) as pool:
            futures = {pool.submit(_check_port, host, p): p for p in ports}
            for i, fut in enumerate(futures):
                if stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                port = futures[fut]
                try:
                    if fut.result():
                        found += 1
                        msg_q.put(("open", port))
                except Exception:
                    pass
                if (i + 1) % 20 == 0 or i + 1 == total:
                    msg_q.put(("progress", (i + 1, total)))
        msg_q.put(("done", f"扫描完成：共发现 {found} 个开放端口"))

    def poll():
        try:
            while True:
                kind, payload = msg_q.get_nowait()
                if kind == "open":
                    tree.insert("", "end", values=(payload, _service_name(payload) or "-", "开放"))
                elif kind == "progress":
                    scanned, total = payload
                    progress_var.set(f"已扫描 {scanned}/{total}……")
                elif kind == "done":
                    running[0] = False
                    btn.config(state="normal")
                    progress_var.set(payload)
                    return
        except queue.Empty:
            pass
        win.after(150, poll)


# ----------------------------------------------------------------------
# 2. 局域网主机发现
# ----------------------------------------------------------------------
def _ping_host(ip):
    """Ping 单个主机，返回是否在线。"""
    try:
        proc = subprocess.run(["ping", "-n", "1", "-w", "400", ip],
                              capture_output=True, text=True, timeout=3)
        return proc.returncode == 0
    except Exception:
        return False


def _get_mac_map():
    """解析 arp -a 输出，返回 {ip: mac}。"""
    mac_map = {}
    try:
        proc = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                mac_map[parts[0]] = parts[1]
    except Exception:
        pass
    return mac_map


def subnet_scan(parent):
    """局域网主机发现工具。"""
    win = _open_tool_window(parent, "局域网主机发现", 560, 480)
    net_var = tk.StringVar(value="192.168.1")
    progress_var = tk.StringVar(value="就绪")
    msg_q = queue.Queue()
    stop_event = threading.Event()
    running = [False]

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="网段（前 3 段）：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=net_var, font=("Consolas", 10), width=16).pack(side="left")
    btn = tk.Button(top, text="开始扫描", command=lambda: start(),
                    font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                    relief="flat", padx=14, cursor="hand2")
    btn.pack(side="left", padx=(10, 0))
    tk.Button(top, text="停止", command=lambda: stop_event.set(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(8, 0))

    listbox = tk.Listbox(win, font=("Consolas", 10), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    listbox.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Label(win, textvariable=progress_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#1f2a3a", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def start():
        if running[0]:
            return
        net = net_var.get().strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){2}", net):
            messagebox.showwarning("主机发现", "请输入网段前 3 段，如 192.168.1")
            return
        listbox.delete(0, "end")
        progress_var.set("正在扫描 1~254……")
        running[0] = True
        btn.config(state="disabled")
        stop_event.clear()
        threading.Thread(target=worker, args=(net,), daemon=True).start()
        win.after(200, poll)

    def worker(net):
        ips = [f"{net}.{i}" for i in range(1, 255)]
        alive = []
        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = {pool.submit(_ping_host, ip): ip for ip in ips}
            for i, fut in enumerate(futures):
                if stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                ip = futures[fut]
                try:
                    if fut.result():
                        alive.append(ip)
                        msg_q.put(("host", ip))
                except Exception:
                    pass
                if (i + 1) % 25 == 0:
                    msg_q.put(("progress", i + 1))
        # 用 ARP 表补充 MAC
        mac_map = _get_mac_map()
        for ip in alive:
            hostname = "-"
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except Exception:
                pass
            mac = mac_map.get(ip, "-")
            msg_q.put(("detail", (ip, hostname, mac)))
        msg_q.put(("done", f"扫描完成：发现 {len(alive)} 台在线主机"))

    def poll():
        try:
            while True:
                kind, payload = msg_q.get_nowait()
                if kind == "host":
                    progress_var.set(f"发现在线主机：{payload}")
                elif kind == "detail":
                    ip, hostname, mac = payload
                    listbox.insert("end", f"{ip:16s} {hostname:24s} {mac}")
                elif kind == "progress":
                    progress_var.set(f"已探测 {payload}/254……")
                elif kind == "done":
                    running[0] = False
                    btn.config(state="normal")
                    progress_var.set(payload)
                    return
        except queue.Empty:
            pass
        win.after(200, poll)


# ----------------------------------------------------------------------
# 3. 路由追踪
# ----------------------------------------------------------------------
def traceroute(parent):
    """路由追踪工具（tracert -d）。"""
    win = _open_tool_window(parent, "路由追踪", 600, 460)
    host_var = tk.StringVar(value="www.baidu.com")
    status_var = tk.StringVar(value="就绪")
    proc_holder = [None]
    running = [False]
    msg_q = queue.Queue()

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="目标：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=host_var, font=("Consolas", 10), width=24).pack(side="left")
    start_btn = tk.Button(top, text="开始", command=lambda: start(),
                          font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                          relief="flat", padx=14, cursor="hand2")
    start_btn.pack(side="left", padx=(10, 0))
    stop_btn = tk.Button(top, text="停止", command=lambda: stop(),
                         font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
                         relief="flat", padx=14, state="disabled", cursor="hand2")
    stop_btn.pack(side="left", padx=(8, 0))

    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="none",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def append_line(line):
        text.configure(state="normal")
        text.insert("end", line + "\n")
        text.see("end")
        text.configure(state="disabled")

    def start():
        if running[0]:
            return
        host = host_var.get().strip() or "127.0.0.1"
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.configure(state="disabled")
        append_line(f"tracert -d -h 30 {host}")
        running[0] = True
        start_btn.config(state="disabled")
        stop_btn.config(state="normal")
        threading.Thread(target=worker, args=(host,), daemon=True).start()
        win.after(200, poll)

    def worker(host):
        try:
            proc = subprocess.Popen(
                ["tracert", "-d", "-h", "30", host],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            proc_holder[0] = proc
            for line in proc.stdout:
                msg_q.put(line.rstrip())
            proc.wait()
        except Exception as exc:
            msg_q.put(f"tracert 执行失败：{exc}")
        msg_q.put(None)

    def stop():
        if proc_holder[0]:
            try:
                proc_holder[0].terminate()
            except Exception:
                pass

    def poll():
        try:
            while True:
                item = msg_q.get_nowait()
                if item is None:
                    running[0] = False
                    start_btn.config(state="normal")
                    stop_btn.config(state="disabled")
                    status_var.set("完成 / 已停止")
                    return
                append_line(item)
        except queue.Empty:
            pass
        win.after(200, poll)


# ----------------------------------------------------------------------
# 4. WHOIS 查询（RDAP）
# ----------------------------------------------------------------------
_RDAP_ENDPOINTS = [
    "https://rdap.verisign.com/com/v1/domain/{d}",
    "https://rdap.verisign.com/net/v1/domain/{d}",
    "https://rdap.org/domain/{d}",
    "https://rdap.apnic.net/domain/{d}",
    "https://rdap.cnnic.cn/domain/{d}",
]


def _rdap_query(domain):
    """RDAP 查询域名注册信息；返回 (文本结果, 是否成功)。"""
    if requests is None:
        return "未安装 requests，无法查询。\n请先执行：pip install requests", False
    for tmpl in _RDAP_ENDPOINTS:
        try:
            resp = requests.get(tmpl.format(d=domain), timeout=10)
            if resp.status_code == 404:
                continue  # 该注册局没有此域名
            if resp.status_code == 200:
                data = resp.json()
                lines = [f"域名: {data.get('ldhName', domain)}"]
                status = data.get("status")
                if status:
                    lines.append(f"状态: {', '.join(status)}")
                for event in data.get("events", []):
                    lines.append(f"{event.get('eventAction', '')}: {event.get('eventDate', '')[:10]}")
                for entity in data.get("entities", []):
                    roles = ",".join(entity.get("roles", []))
                    vcard = entity.get("vcardArray", [None, []])[1]
                    name = ""
                    for item in vcard:
                        if item[0] == "fn":
                            name = item[3]
                    if roles and name:
                        lines.append(f"{roles}: {name}")
                nameservers = data.get("nameservers")
                if nameservers:
                    lines.append("NS: " + ", ".join(ns.get("ldhName", "") for ns in nameservers))
                return "\n".join(lines), True
        except Exception:
            continue
    return "未查询到该域名的注册信息（域名可能不存在，或注册局接口不可达）", False


def whois_lookup(parent):
    """WHOIS 查询工具（RDAP 协议）。"""
    win = _open_tool_window(parent, "WHOIS 查询", 560, 420)
    domain_var = tk.StringVar(value="qq.com")
    status_var = tk.StringVar(value="就绪")

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="域名：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=domain_var, font=("Consolas", 10), width=24).pack(side="left")
    tk.Button(top, text="查询", command=lambda: query(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))

    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="word",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def query():
        domain = domain_var.get().strip().lower()
        if not domain:
            messagebox.showwarning("WHOIS", "请输入域名。")
            return
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", "查询中……")
        text.configure(state="disabled")
        status_var.set("正在查询……")
        _run_in_thread(win, lambda: _rdap_query(domain), on_done)

    def on_done(kind, payload):
        if kind == "error":
            result, ok = f"查询失败：{payload}", False
        else:
            result, ok = payload
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", result)
        text.configure(state="disabled")
        status_var.set("查询完成" if ok else "未查询到结果")


# ----------------------------------------------------------------------
# 5. DNS 解析查询
# ----------------------------------------------------------------------
def dns_lookup(parent):
    """DNS 解析查询工具（nslookup）。"""
    win = _open_tool_window(parent, "DNS 查询", 600, 440)
    domain_var = tk.StringVar(value="www.baidu.com")
    type_var = tk.StringVar(value="A")
    status_var = tk.StringVar(value="就绪")

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="域名：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=domain_var, font=("Consolas", 10), width=22).pack(side="left")
    ttk.Combobox(top, textvariable=type_var, values=["A", "AAAA", "MX", "NS", "TXT", "CNAME"],
                 state="readonly", width=8).pack(side="left", padx=(8, 0))
    tk.Button(top, text="查询", command=lambda: query(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))

    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="none",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def query():
        domain = domain_var.get().strip()
        if not domain:
            messagebox.showwarning("DNS 查询", "请输入域名。")
            return
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", f"nslookup -type={type_var.get()} {domain}\n\n查询中……")
        text.configure(state="disabled")
        status_var.set("正在查询……")
        _run_in_thread(win, lambda: _nslookup(domain, type_var.get()), on_done)

    def on_done(kind, payload):
        if kind == "error":
            result = f"nslookup 执行失败：{payload}"
        else:
            result = payload
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", result)
        text.configure(state="disabled")
        status_var.set("查询完成")


def _nslookup(domain, rtype):
    """执行 nslookup，返回过滤后的输出文本。"""
    try:
        proc = subprocess.run(["nslookup", "-type=" + rtype, domain],
                              capture_output=True, text=True, timeout=15,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as exc:
        raise RuntimeError(str(exc))
    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    return "\n".join(lines) if lines else "(无输出)"


# ----------------------------------------------------------------------
# 6. HTTP 安全头检测
# ----------------------------------------------------------------------
_SECURITY_HEADERS = [
    ("Content-Security-Policy", "CSP 内容安全策略"),
    ("X-Frame-Options", "防点击劫持"),
    ("X-Content-Type-Options", "防 MIME 嗅探"),
    ("Strict-Transport-Security", "HSTS 强制 HTTPS"),
    ("Referrer-Policy", "来源策略"),
    ("X-XSS-Protection", "XSS 过滤"),
]


def _http_header_check(url):
    """请求 URL，返回 (摘要行列表, 全部头文本)。"""
    if requests is None:
        raise RuntimeError("未安装 requests，无法检测。\n请先执行：pip install requests")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    resp = requests.get(url, timeout=10, allow_redirects=True, verify=True)
    lines = [f"URL: {resp.url}", f"状态码: {resp.status_code}",
             f"服务器: {resp.headers.get('Server', '-')}"]
    for header, desc in _SECURITY_HEADERS:
        value = resp.headers.get(header)
        if value:
            lines.append(f"[有] {header}（{desc}）")
        else:
            lines.append(f"[缺] {header}（{desc}）")
    raw = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
    return lines, raw


def http_header(parent):
    """HTTP 安全头检测工具。"""
    win = _open_tool_window(parent, "HTTP 安全头检测", 600, 460)
    url_var = tk.StringVar(value="https://www.baidu.com")
    status_var = tk.StringVar(value="就绪")

    top = tk.Frame(win, bg="#f5f6fa")
    top.pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(top, text="URL：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(top, textvariable=url_var, font=("Consolas", 10), width=30).pack(side="left")
    tk.Button(top, text="检测", command=lambda: check(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))

    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="none",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699", anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def check():
        url = url_var.get().strip()
        if not url:
            messagebox.showwarning("安全头检测", "请输入 URL。")
            return
        status_var.set("正在检测……")
        _run_in_thread(win, lambda: _http_header_check(url), on_done)

    def on_done(kind, payload):
        if kind == "error":
            status_var.set(f"检测失败：{payload}")
            return
        summary, raw = payload
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", "\n".join(summary) + "\n\n==== 全部响应头 ====\n" + raw)
        text.configure(state="disabled")
        status_var.set("检测完成")


# ----------------------------------------------------------------------
# 7. 密码强度检测
# ----------------------------------------------------------------------
# 常见弱密码（部分），命中直接判为极弱
_WEAK_PASSWORDS = {
    "123456", "password", "123456789", "12345678", "12345", "111111",
    "1234567", "sunshine", "qwerty", "iloveyou", "princess", "admin",
    "welcome", "monkey", "login", "abc123", "starwars", "123123",
    "dragon", "passw0rd", "master", "hello", "freedom", "whatever",
    "qazwsx", "trustno1", "666666", "88888888", "000000", "a123456",
}


def _password_strength(pwd):
    """评估密码强度，返回 (得分 0-100, 说明列表)。"""
    if not pwd:
        return 0, ["密码为空"]
    notes = []
    score = 0
    length = len(pwd)
    if length >= 12:
        score += 30
    elif length >= 8:
        score += 20
    elif length >= 6:
        score += 10
    else:
        notes.append("长度过短（建议 ≥ 12 位）")
    if re.search(r"[a-z]", pwd):
        score += 15
    if re.search(r"[A-Z]", pwd):
        score += 15
    if re.search(r"\d", pwd):
        score += 15
    if re.search(r"[^A-Za-z0-9]", pwd):
        score += 15
    if pwd.lower() in _WEAK_PASSWORDS:
        return 0, ["命中常见弱密码库，请立即更换"]
    if re.search(r"(.)\1{2,}", pwd):
        notes.append("存在连续重复字符")
    if re.search(r"(0123|1234|2345|3456|4567|5678|6789|qwerty|asdf|zxcv|1qaz|2wsx)",
                 pwd.lower()):
        notes.append("包含常见键盘顺序")
    if len(set(pwd)) < max(3, length // 2):
        notes.append("字符种类偏少")
    score = min(score, 100)
    if score >= 80:
        grade = "很强"
    elif score >= 60:
        grade = "较强"
    elif score >= 40:
        grade = "一般"
    else:
        grade = "较弱"
    notes.insert(0, f"评级：{grade}（{score} 分）")
    return score, notes


def password_strength(parent):
    """密码强度检测工具。"""
    win = _open_tool_window(parent, "密码强度检测", 480, 340)
    win.resizable(False, False)
    pwd_var = tk.StringVar()
    show_var = tk.BooleanVar(value=False)
    result_var = tk.StringVar(value="请输入密码后点击“检测”")

    row = tk.Frame(win, bg="#f5f6fa")
    row.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(row, text="密码：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    pwd_entry = tk.Entry(row, textvariable=pwd_var, font=("Consolas", 11),
                         show="*", width=24)
    pwd_entry.pack(side="left")
    tk.Checkbutton(row, text="显示", variable=show_var, bg="#f5f6fa",
                   command=lambda: pwd_entry.config(show="" if show_var.get() else "*")).pack(side="left")

    tk.Button(win, text="检测", command=lambda: check(),
              font=("Microsoft YaHei UI", 11), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=16, pady=4, cursor="hand2").pack(pady=(4, 8))
    result_label = tk.Label(win, textvariable=result_var, font=("Microsoft YaHei UI", 11),
                            bg="#ffffff", fg="#1f2a3a", anchor="w", justify="left",
                            relief="solid", bd=1, padx=8)
    result_label.pack(fill="x", padx=14, pady=(0, 8))
    tk.Label(win, text="按长度、字符种类、常见弱密码库与键盘顺序综合评估",
             font=("Microsoft YaHei UI", 9), bg="#f5f6fa", fg="#7a8699").pack(pady=(0, 10))

    def check():
        score, notes = _password_strength(pwd_var.get())
        color = "#c0392b" if score < 40 else ("#e67e22" if score < 60
                                              else ("#f1c40f" if score < 80 else "#27ae60"))
        result_var.set("\n".join(notes))
        result_label.config(fg=color)


# ----------------------------------------------------------------------
# 8. 哈希计算与弱密码字典比对
# ----------------------------------------------------------------------
def _hash_text(text):
    """计算文本的 MD5 / SHA-1 / SHA-256 / SHA-512，返回字典。"""
    import hashlib
    data = text.encode("utf-8", errors="replace")
    return {
        "MD5": hashlib.md5(data).hexdigest(),
        "SHA-1": hashlib.sha1(data).hexdigest(),
        "SHA-256": hashlib.sha256(data).hexdigest(),
        "SHA-512": hashlib.sha512(data).hexdigest(),
    }


def _md5_weak_match(md5hex):
    """若 MD5 命中内置弱密码库，返回对应明文；否则 None。"""
    import hashlib
    target = md5hex.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", target):
        return None
    for pwd in _WEAK_PASSWORDS:
        if hashlib.md5(pwd.encode()).hexdigest() == target:
            return pwd
    return None


def hash_tools(parent):
    """哈希计算与弱密码比对工具。"""
    win = _open_tool_window(parent, "哈希计算", 560, 460)
    input_text = tk.Text(win, font=("Consolas", 10), height=5, relief="solid", bd=1)
    result_var = tk.StringVar(value="--")

    tk.Label(win, text="输入文本（或粘贴 MD5 用于弱密码比对）：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(anchor="w", padx=12, pady=(12, 2))
    input_text.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(win, text="计算哈希", command=lambda: compute(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(anchor="w", padx=12, pady=(0, 6))
    tk.Label(win, textvariable=result_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="w", justify="left", relief="solid", bd=1,
             padx=8).pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def compute():
        text = input_text.get("1.0", "end-1c")
        if not text:
            messagebox.showwarning("哈希计算", "请输入内容。")
            return
        # 若输入是 MD5，尝试弱密码比对
        match = _md5_weak_match(text)
        if match is not None:
            result_var.set(f"命中弱密码！明文为：{match}")
            return
        hashes = _hash_text(text)
        result_var.set("\n".join(f"{k}: {v}" for k, v in hashes.items()))


# ----------------------------------------------------------------------
# 9. IP 归属地查询
# ----------------------------------------------------------------------
def _ip_geo(ip):
    """查询 IP 归属地；返回文本结果。"""
    if requests is None:
        return "未安装 requests，无法查询。\n请先执行：pip install requests"
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=10)
        data = resp.json()
        if data.get("status") == "success":
            fields = [("国家/地区", data.get("country")), ("省/州", data.get("regionName")),
                      ("城市", data.get("city")), ("运营商", data.get("isp")),
                      ("组织", data.get("org")), ("ASN", data.get("as")),
                      ("经纬度", f"{data.get('lat')}, {data.get('lon')}"),
                      ("时区", data.get("timezone"))]
            return "\n".join(f"{k}: {v}" for k, v in fields if v)
        return f"查询失败：{data.get('message', '未知错误')}"
    except Exception as exc:
        return f"查询失败：{exc}"


def ip_geo(parent):
    """IP 归属地查询工具。"""
    win = _open_tool_window(parent, "IP 归属地", 480, 360)
    ip_var = tk.StringVar()
    result_var = tk.StringVar(value="--")

    row = tk.Frame(win, bg="#f5f6fa")
    row.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(row, text="IP：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(row, textvariable=ip_var, font=("Consolas", 10), width=20).pack(side="left")
    tk.Button(row, text="查询", command=lambda: query(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Button(row, text="我的 IP", command=lambda: my_ip(),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", fg="#1f2a3a",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(8, 0))

    tk.Label(win, textvariable=result_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="nw", justify="left", relief="solid", bd=1,
             padx=8).pack(fill="both", expand=True, padx=14, pady=(0, 8))
    tk.Label(win, text="数据来源：ip-api.com（免费接口）", font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699").pack(pady=(0, 10))

    def query():
        ip = ip_var.get().strip()
        if not ip:
            messagebox.showwarning("IP 归属地", "请输入 IP 地址。")
            return
        result_var.set("查询中……")
        _run_in_thread(win, lambda: _ip_geo(ip), on_done)

    def my_ip():
        from tools_network import _get_external_ip
        ip = _get_external_ip()
        # 提取 IP（ipip 返回文本“当前 IP：x.x.x.x 来自于…”）
        m = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", ip)
        ip_var.set(m.group(0) if m else ip)
        if m:
            query()

    def on_done(kind, payload):
        result_var.set(payload if kind == "ok" else f"查询失败：{payload}")


# ----------------------------------------------------------------------
# 10. 网络连接状态
# ----------------------------------------------------------------------
def _net_connections():
    """获取连接状态行；psutil 优先，缺失时解析 netstat -ano。"""
    rows = []
    if psutil:
        try:
            for c in psutil.net_connections(kind="inet"):
                try:
                    name = psutil.Process(c.pid).name() if c.pid else ""
                except Exception:
                    name = ""
                laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
                raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
                rows.append((c.type.name, laddr, raddr, c.status, c.pid or "-", name))
            return rows
        except Exception:
            pass
    try:
        proc = subprocess.run(["netstat", "-ano"],
                              capture_output=True, text=True, timeout=15,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and re.match(r"^(TCP|UDP)", parts[0]):
                proto = parts[0]
                laddr = parts[1]
                raddr = parts[2] if proto == "TCP" else "*"
                state = parts[3] if proto == "TCP" else "UDP"
                pid = parts[-1]
                rows.append((proto, laddr, raddr, state, pid, ""))
    except Exception:
        pass
    return rows


def net_stat(parent):
    """网络连接状态工具。"""
    win = _open_tool_window(parent, "网络连接状态", 720, 500)
    tree = ttk.Treeview(win, columns=("proto", "laddr", "raddr", "state", "pid", "name"),
                        show="headings")
    for col, text, width in (("proto", "协议", 60), ("laddr", "本地地址", 160),
                             ("raddr", "远程地址", 160), ("state", "状态", 110),
                             ("pid", "PID", 70), ("name", "进程名", 120)):
        tree.heading(col, text=text)
        tree.column(col, width=width, anchor="center" if col in ("proto", "state", "pid") else "w")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(12, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(12, 6))

    btn_row = tk.Frame(win, bg="#f5f6fa")
    btn_row.pack(fill="x", padx=12, pady=(0, 4))
    btn = tk.Button(btn_row, text="刷新", command=lambda: refresh(),
                    font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
                    relief="flat", padx=14, cursor="hand2")
    btn.pack(side="left")
    status_var = tk.StringVar(value="就绪")
    tk.Label(btn_row, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg="#f5f6fa", fg="#7a8699").pack(side="left", padx=(10, 0))

    def refresh():
        btn.config(state="disabled")
        status_var.set("读取中……")
        _run_in_thread(win, _net_connections, on_done)

    def on_done(kind, payload):
        btn.config(state="normal")
        if kind == "error":
            status_var.set(f"读取失败：{payload}")
            return
        tree.delete(*tree.get_children())
        for row in payload[:800]:
            tree.insert("", "end", values=row)
        status_var.set(f"共 {len(payload)} 条连接（最多显示 800 条）")

    refresh()
