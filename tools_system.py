# -*- coding: utf-8 -*-
"""
tools_system.py —— 系统工具集（10 个实用工具）

每个工具是一个函数，签名统一为 func(parent)：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

工具列表：
    1. calc(parent)            简单计算器
    2. sysinfo(parent)         系统信息（platform / psutil，psutil 缺失时降级）
    3. power_control(parent)   关机 / 重启 / 休眠 / 睡眠
    4. process_manager(parent) 进程列表与结束进程（无权限时提示管理员）
    5. hosts_editor(parent)    编辑 hosts 文件（需管理员权限）
    6. disk_speed_test(parent) 测试 C/D 盘读写速度
    7. batch_rename(parent)    批量重命名
    8. md5_checker(parent)     MD5 / SHA-256 校验
    9. restore_point(parent)   创建系统还原点（不可用时提示）
   10. startup_manager(parent) 管理开机启动项（注册表 Run 键）

依赖说明：
    - psutil 可选：安装后系统信息/进程管理器显示更全，未安装时自动降级
      （平台信息 + ctypes 内存 + tasklist 进程列表）。
    - 需要管理员权限的功能（hosts 保存、HKLM 启动项、还原点、结束系统进程）
      失败时会给出明确提示。
"""
import csv
import hashlib
import io
import os
import platform
import queue
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import winreg

try:
    import psutil
except ImportError:
    psutil = None  # 可选依赖

# ---------- 常量 ----------
HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
RUN_KEYS = {
    "HKCU": r"Software\Microsoft\Windows\CurrentVersion\Run",
    "HKLM": r"Software\Microsoft\Windows\CurrentVersion\Run",
}
_BG = "#f5f6fa"
_TITLE_FG = "#1f2a3a"
_HINT_FG = "#7a8699"
_BTN_BG = "#3d5a80"
_BTN_FG = "#ffffff"


# ----------------------------------------------------------------------
# 通用辅助
# ----------------------------------------------------------------------
def _open_tool_window(parent, title, width, height):
    """创建并返回一个标准配置的 Toplevel 工具窗口。"""
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=_BG)
    win.resizable(True, True)
    win.minsize(300, 200)
    # 偏移父窗口一点，避免完全重叠
    try:
        x = parent.winfo_rootx() + 80
        y = parent.winfo_rooty() + 60
        win.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError:
        win.geometry(f"{width}x{height}")
    # 尝试复用 PCM 图标
    try:
        import utils
        win.iconbitmap(utils.ensure_icon())
    except Exception:
        pass
    return win


def _run_in_thread(win, func, on_done):
    """在后台线程执行 func，完成后在主线程回调 on_done(result)。

    通过“队列 + after() 轮询”实现线程安全，用于耗时操作。
    """
    q = queue.Queue()

    def worker():
        try:
            q.put(("ok", func()))
        except Exception as exc:
            q.put(("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            win.after(100, poll)
            return
        on_done(kind, payload)

    win.after(100, poll)


# ----------------------------------------------------------------------
# 1. 简单计算器
# ----------------------------------------------------------------------
def _is_safe_expr(expr: str) -> bool:
    """校验表达式只包含数字、运算符与括号（防止任意代码执行）。"""
    import re
    return bool(re.fullmatch(r"[0-9+\-*/().\s]+", expr))


def calc(parent):
    """简单计算器工具。"""
    win = _open_tool_window(parent, "PCM 计算器", 320, 380)
    win.resizable(False, False)

    expr_var = tk.StringVar()
    entry = tk.Entry(win, textvariable=expr_var, font=("Consolas", 14),
                     justify="right", relief="solid", bd=1)
    entry.pack(fill="x", padx=10, pady=(12, 6))

    # 按钮放在独立 Frame 中，避免与 Entry 的 pack 混用几何管理器
    btn_frame = tk.Frame(win, bg=_BG)
    btn_frame.pack(fill="both", expand=True, padx=6, pady=(0, 10))

    def append(ch):
        expr_var.set(expr_var.get() + ch)
        entry.icursor("end")

    def backspace():
        expr_var.set(expr_var.get()[:-1])

    def clear():
        expr_var.set("")

    def evaluate():
        expr = expr_var.get().strip()
        if not _is_safe_expr(expr):
            expr_var.set("错误：非法表达式")
            return
        try:
            result = eval(expr, {"__builtins__": {}}, {})  # 已做字符白名单校验
            expr_var.set(str(result))
        except ZeroDivisionError:
            expr_var.set("错误：除数为 0")
        except Exception:
            expr_var.set("错误：表达式无效")

    # 按钮布局：数字 / 运算符 / 括号 / 控制键
    keys = [
        ("7", "8", "9", "/"),
        ("4", "5", "6", "*"),
        ("1", "2", "3", "-"),
        ("0", ".", "=", "+"),
        ("(", ")", "C", "⌫"),
    ]
    for r, row in enumerate(keys):
        for c, key in enumerate(row):
            if key == "=":
                cmd = evaluate
            elif key == "C":
                cmd = clear
            elif key == "⌫":
                cmd = backspace
            else:
                cmd = lambda k=key: append(k)
            tk.Button(btn_frame, text=key, command=cmd, font=("Microsoft YaHei UI", 12),
                      bg="#ffffff", activebackground="#d9e2f0", relief="flat",
                      cursor="hand2").grid(row=r + 1, column=c, sticky="nsew",
                                           padx=3, pady=3)
    for i in range(4):
        btn_frame.grid_columnconfigure(i, weight=1)
    for i in range(1, 6):
        btn_frame.grid_rowconfigure(i, weight=1)

    entry.bind("<Return>", lambda e: evaluate())
    entry.focus_set()


# ----------------------------------------------------------------------
# 2. 系统信息
# ----------------------------------------------------------------------
def _get_memory_mb():
    """返回 (total_mb, used_mb)；失败返回 None。psutil 缺失时用 ctypes。"""
    if psutil:
        try:
            vm = psutil.virtual_memory()
            return vm.total / 1048576, (vm.total - vm.available) / 1048576
        except Exception:
            return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_mb = stat.ullTotalPhys / 1048576
        used_mb = (stat.ullTotalPhys - stat.ullAvailPhys) / 1048576
        return total_mb, used_mb
    except Exception:
        return None


def _collect_sysinfo():
    """收集系统信息，返回 [(字段, 值), ...] 列表（便于测试）。"""
    info = []
    info.append(("操作系统", f"{platform.system()} {platform.release()}"))
    info.append(("系统版本", platform.version()))
    info.append(("机器类型", platform.machine()))
    info.append(("处理器", platform.processor() or "未知"))
    info.append(("主机名", socket.gethostname()))
    info.append(("Python", platform.python_version()))

    # CPU
    cores = os.cpu_count()
    info.append(("CPU 逻辑核心数", f"{cores} 核" if cores else "未知"))
    if psutil:
        try:
            info.append(("CPU 使用率", f"{psutil.cpu_percent(interval=0.3)}%"))
        except Exception:
            pass
    else:
        info.append(("CPU 使用率", "（安装 psutil 后可显示）"))

    # 内存
    mem = _get_memory_mb()
    if mem:
        total_mb, used_mb = mem
        info.append(("物理内存", f"{total_mb / 1024:.1f} GB（已用 {used_mb / 1024:.1f} GB）"))
    else:
        info.append(("物理内存", "获取失败"))

    # 启动时间
    if psutil:
        try:
            boot = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(psutil.boot_time()))
            info.append(("开机时间", boot))
        except Exception:
            pass

    # 磁盘（C: 起的所有固定盘）
    drives = [d for d in ("C:", "D:", "E:", "F:", "G:")
              if os.path.exists(d + "\\")]
    for drive in drives:
        try:
            usage = shutil.disk_usage(drive + "\\")
            used_gb = usage.used / 1073741824
            total_gb = usage.total / 1073741824
            pct = usage.used / usage.total * 100 if usage.total else 0
            info.append((f"磁盘 {drive}", f"{used_gb:.1f} / {total_gb:.1f} GB（{pct:.1f}%）"))
        except OSError:
            info.append((f"磁盘 {drive}", "读取失败"))
    return info


def sysinfo(parent):
    """系统信息工具。"""
    win = _open_tool_window(parent, "系统信息", 620, 520)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(top, text="本机系统信息", font=("Microsoft YaHei UI", 12, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Button(top, text="刷新", command=lambda: _fill(), font=("Microsoft YaHei UI", 10),
              bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=12,
              cursor="hand2").pack(side="right")

    text = tk.Text(win, font=("Consolas", 10), state="disabled",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1, wrap="word")
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 12))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))

    tip = tk.Label(win, text="提示：安装 psutil（pip install psutil）可显示 CPU 使用率等更多信息",
                   font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG)
    tip.pack(side="bottom", anchor="w", padx=12, pady=(0, 8))

    def _fill():
        text.configure(state="normal")
        text.delete("1.0", "end")
        for field, value in _collect_sysinfo():
            text.insert("end", f"{field}：{value}\n")
        text.configure(state="disabled")

    _fill()


# ----------------------------------------------------------------------
# 3. 电源控制
# ----------------------------------------------------------------------
def power_control(parent):
    """关机 / 重启 / 休眠 / 睡眠工具。"""
    win = _open_tool_window(parent, "电源控制", 420, 300)
    win.resizable(False, False)

    tk.Label(win, text="电源控制", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(16, 4))
    tk.Label(win, text="关机/重启会延迟 5 秒执行，可在期间点“取消”",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 12))

    actions = [
        ("关机", "shutdown /s /t 5", "关机"),
        ("重启", "shutdown /r /t 5", "重启"),
        ("休眠", "shutdown /h", "休眠"),
        ("睡眠", "rundll32.exe powrprof.dll,SetSuspendState 0,1,0", "睡眠"),
    ]

    def do(cmd, desc):
        if messagebox.askyesno("电源控制", f"确定要{desc}吗？"):
            try:
                subprocess.Popen(cmd, shell=True)
            except Exception as exc:
                messagebox.showerror("电源控制", f"执行失败：{exc}")

    for text, cmd, desc in actions:
        tk.Button(win, text=text, command=lambda c=cmd, d=desc: do(c, d),
                  font=("Microsoft YaHei UI", 12), bg=_BTN_BG, fg=_BTN_FG,
                  activebackground="#5a7fb8", relief="flat", pady=8,
                  cursor="hand2").pack(fill="x", padx=40, pady=4)

    tk.Button(win, text="取消已计划的关机/重启", command=lambda: subprocess.Popen("shutdown /a", shell=True),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", fg="#1f2a3a",
              relief="flat", pady=4, cursor="hand2").pack(fill="x", padx=40, pady=(10, 4))
    tk.Label(win, text="提示：休眠/睡眠可能受系统电源策略影响；部分操作需要相应权限",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(4, 8))


# ----------------------------------------------------------------------
# 4. 进程管理器
# ----------------------------------------------------------------------
def _parse_tasklist(text):
    """解析 tasklist /FO CSV /NH 输出，返回 [(pid, name, 0.0, mem_mb), ...]。"""
    result = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 5:
            name = row[0].strip('"')
            try:
                pid = int(row[1].strip('"'))
            except ValueError:
                continue
            mem_text = row[4].strip('"').replace(" K", "").replace(",", "")
            try:
                mem_mb = round(float(mem_text) / 1024, 1)
            except ValueError:
                mem_mb = 0.0
            result.append((pid, name, 0.0, mem_mb))
    return result


def _list_processes():
    """返回 [(pid, name, cpu_percent, mem_mb), ...]；psutil 缺失时用 tasklist。"""
    if psutil:
        result = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                pinfo = proc.info
                mem_mb = (pinfo["memory_info"].rss / 1048576) if pinfo["memory_info"] else 0.0
                result.append((pinfo["pid"], pinfo["name"],
                               pinfo["cpu_percent"] or 0.0, round(mem_mb, 1)))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        result.sort(key=lambda x: x[1].lower())
        return result

    # 降级：tasklist /FO CSV（无 CPU 占用率）
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        result = _parse_tasklist(out)
        result.sort(key=lambda x: x[1].lower())
        return result
    except Exception:
        return []


def _kill_process(pid):
    """结束进程；无权限时抛 PermissionError。"""
    if psutil:
        try:
            psutil.Process(pid).kill()
        except psutil.AccessDenied:
            raise PermissionError("需要管理员权限")
        except psutil.NoSuchProcess:
            raise FileNotFoundError("进程已退出")
    else:
        proc = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            err = proc.stderr.strip() or "结束进程失败"
            if "拒绝" in err or "denied" in err.lower():
                raise PermissionError("需要管理员权限")
            raise RuntimeError(err)


def process_manager(parent):
    """进程管理器工具。"""
    win = _open_tool_window(parent, "进程管理器", 640, 480)

    tree = ttk.Treeview(win, columns=("name", "pid", "cpu", "mem"), show="headings")
    tree.heading("name", text="进程名")
    tree.heading("pid", text="PID")
    tree.heading("cpu", text="CPU%")
    tree.heading("mem", text="内存(MB)")
    tree.column("name", width=260)
    tree.column("pid", width=80, anchor="center")
    tree.column("cpu", width=70, anchor="center")
    tree.column("mem", width=90, anchor="center")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))

    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(btn_row, text="刷新列表", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="结束选中进程", command=lambda: kill_selected(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Label(win, text="提示：结束系统关键进程或高权限进程需要管理员权限",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=12, pady=(0, 10))

    def refresh():
        tree.delete(*tree.get_children())
        for pid, name, cpu, mem in _list_processes():
            tree.insert("", "end", iid=str(pid),
                        values=(name, pid, f"{cpu:.1f}" if cpu else "-", mem))

    def kill_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("进程管理器", "请先在列表中选择一个进程。")
            return
        pid = int(sel[0])
        name = tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("进程管理器", f"确定结束进程“{name}”（PID {pid}）吗？"):
            return
        try:
            _kill_process(pid)
            messagebox.showinfo("进程管理器", f"已结束进程 {name}（PID {pid}）")
            refresh()
        except PermissionError:
            messagebox.showerror("进程管理器", "结束失败：需要管理员权限。\n请以管理员身份运行 PCM。")
        except FileNotFoundError as exc:
            messagebox.showinfo("进程管理器", str(exc))
        except Exception as exc:
            messagebox.showerror("进程管理器", f"结束失败：{exc}")

    refresh()


# ----------------------------------------------------------------------
# 5. Hosts 编辑器
# ----------------------------------------------------------------------
def hosts_editor(parent):
    """编辑 hosts 文件（保存需要管理员权限）。"""
    win = _open_tool_window(parent, "Hosts 文件编辑器", 640, 480)

    tk.Label(win, text=f"文件：{HOSTS_PATH}",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=12, pady=(10, 2))

    text = tk.Text(win, font=("Consolas", 10), wrap="none",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(4, 6))

    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(fill="x", padx=12, pady=(0, 6))
    tk.Button(btn_row, text="刷新", command=lambda: load(), font=("Microsoft YaHei UI", 10),
              bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=12,
              cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="保存", command=lambda: save(), font=("Microsoft YaHei UI", 10),
              bg="#27ae60", fg="#ffffff", relief="flat", padx=12,
              cursor="hand2").pack(side="left", padx=(10, 0))

    status = tk.Label(win, text="", font=("Microsoft YaHei UI", 9),
                      bg=_BG, fg=_HINT_FG, anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 8))

    def load():
        try:
            with open(HOSTS_PATH, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except PermissionError:
            status.config(text="无权限读取 hosts 文件，请以管理员身份运行 PCM。")
            return
        except OSError as exc:
            status.config(text=f"读取失败：{exc}")
            return
        text.delete("1.0", "end")
        text.insert("1.0", content)
        status.config(text="已加载（保存需要管理员权限）")

    def save():
        content = text.get("1.0", "end-1c")
        try:
            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            messagebox.showerror("Hosts 编辑器",
                                 "保存失败：需要管理员权限。\n请以管理员身份运行 PCM。")
            return
        except OSError as exc:
            messagebox.showerror("Hosts 编辑器", f"保存失败：{exc}")
            return
        status.config(text="已保存")
        messagebox.showinfo("Hosts 编辑器", "hosts 文件已保存。")

    load()


# ----------------------------------------------------------------------
# 6. 磁盘读写测速
# ----------------------------------------------------------------------
def _speed_test(drive, size_mb):
    """测试指定盘符读写速度，返回 (write_mb_per_s, read_mb_per_s, message)。"""
    path = os.path.join(drive, "pcm_speed_test.tmp")
    total = size_mb * 1024 * 1024
    chunk = b"x" * (1024 * 1024)  # 1MB 数据块
    try:
        # 写入测试
        t0 = time.time()
        with open(path, "wb") as f:
            written = 0
            while written < total:
                n = min(len(chunk), total - written)
                f.write(chunk[:n])
                written += n
        t_write = time.time() - t0
        write_speed = total / 1048576 / t_write if t_write > 0 else 0.0

        # 读取测试
        t0 = time.time()
        with open(path, "rb") as f:
            while f.read(1024 * 1024):
                pass
        t_read = time.time() - t0
        read_speed = total / 1048576 / t_read if t_read > 0 else 0.0
        return write_speed, read_speed, ""
    except PermissionError:
        return 0.0, 0.0, f"无权限写入 {drive} 根目录，请以管理员身份运行或更换测试盘符"
    except OSError as exc:
        return 0.0, 0.0, f"测试失败：{exc}"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def disk_speed_test(parent):
    """磁盘读写测速工具。"""
    win = _open_tool_window(parent, "磁盘读写测速", 520, 340)
    win.resizable(False, False)

    drive_var = tk.StringVar(value="C:")
    size_var = tk.StringVar(value="64")
    status_var = tk.StringVar(value="就绪")
    write_var = tk.StringVar(value="--")
    read_var = tk.StringVar(value="--")

    form = tk.Frame(win, bg=_BG)
    form.pack(fill="x", padx=16, pady=(14, 6))
    tk.Label(form, text="测试盘符：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Spinbox(form, from_=1, to=6, textvariable=drive_var, width=4,
               font=("Consolas", 10), values=("C:", "D:", "E:", "F:", "G:")).pack(side="left")
    tk.Label(form, text="   大小 (MB)：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(form, textvariable=size_var, width=8, font=("Consolas", 10)).pack(side="left")

    btn = tk.Button(win, text="开始测试", command=lambda: start(), font=("Microsoft YaHei UI", 11),
                    bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=16, pady=4,
                    cursor="hand2")
    btn.pack(pady=(4, 10))

    # 结果区：写入/读取各占一列，避免窄窗口把“读取速度”数值截断
    result = tk.Frame(win, bg="#ffffff", relief="solid", bd=1)
    result.pack(fill="x", padx=16, pady=(0, 10))
    for col, (text, var, color) in enumerate((("写入速度", write_var, "#27ae60"),
                                              ("读取速度", read_var, "#2980b9"))):
        result.columnconfigure(col, weight=1)
        cell = tk.Frame(result, bg="#ffffff")
        cell.grid(row=0, column=col, sticky="nsew", padx=8, pady=10)
        tk.Label(cell, text=text, font=("Microsoft YaHei UI", 11),
                 bg="#ffffff", fg=_HINT_FG).pack()
        tk.Label(cell, textvariable=var, font=("Microsoft YaHei UI", 15, "bold"),
                 bg="#ffffff", fg=color).pack()

    status = tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
                      bg=_BG, fg=_TITLE_FG)
    status.pack(pady=(0, 8))

    def start():
        drive = drive_var.get().strip().upper()
        if len(drive) < 2 or drive[1] != ":":
            messagebox.showwarning("磁盘测速", "请选择有效的盘符（如 C: 或 D:）。")
            return
        try:
            size_mb = int(size_var.get())
            if size_mb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("磁盘测速", "测试大小必须是正整数（MB）。")
            return
        status_var.set("测试中，请稍候……")
        write_var.set("--")
        read_var.set("--")
        btn.config(state="disabled")
        _run_in_thread(win, lambda: _speed_test(drive, size_mb), on_done)

    def on_done(kind, payload):
        btn.config(state="normal")
        if kind == "error":
            status_var.set(f"测试失败：{payload}")
            return
        write_speed, read_speed, message = payload
        if message:
            status_var.set(message)
        else:
            write_var.set(f"{write_speed:.1f} MB/s")
            read_var.set(f"{read_speed:.1f} MB/s")
            status_var.set(f"测试完成（{size_var.get()} MB）")


# ----------------------------------------------------------------------
# 7. 批量重命名
# ----------------------------------------------------------------------
def _build_rename_plan(directory, prefix="", suffix="", old="", new=""):
    """生成批量重命名计划：返回 [(原名, 新名), ...]（含冲突过滤，便于测试）。"""
    try:
        names = [n for n in os.listdir(directory)
                 if os.path.isfile(os.path.join(directory, n))]
    except OSError:
        return []
    existing = set(names)
    targets = set()
    plan = []
    for name in sorted(names):
        stem, ext = os.path.splitext(name)
        new_stem = stem.replace(old, new) if old else stem
        if prefix:
            new_stem = prefix + new_stem
        if suffix:
            new_stem = new_stem + suffix
        new_name = new_stem + ext
        if (new_name != name and new_name not in existing and new_name not in targets):
            plan.append((name, new_name))
            targets.add(new_name)
    return plan


def batch_rename(parent):
    """批量重命名工具。"""
    win = _open_tool_window(parent, "批量重命名", 560, 520)
    dir_var = tk.StringVar()
    prefix_var = tk.StringVar()
    suffix_var = tk.StringVar()
    old_var = tk.StringVar()
    new_var = tk.StringVar()

    # 目录选择
    row0 = tk.Frame(win, bg=_BG)
    row0.pack(fill="x", padx=14, pady=(12, 4))
    tk.Label(row0, text="目录：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row0, textvariable=dir_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row0, text="浏览…", command=lambda: browse(), font=("Microsoft YaHei UI", 10),
              bg="#aab4c4", relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(6, 0))

    # 规则输入
    rules = tk.Frame(win, bg=_BG)
    rules.pack(fill="x", padx=14, pady=4)
    tk.Label(rules, text="前缀：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=0, column=0, sticky="w")
    tk.Entry(rules, textvariable=prefix_var, width=14).grid(row=0, column=1, padx=(0, 12))
    tk.Label(rules, text="后缀：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=0, column=2, sticky="w")
    tk.Entry(rules, textvariable=suffix_var, width=14).grid(row=0, column=3)
    tk.Label(rules, text="替换：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=1, column=0, sticky="w", pady=(4, 0))
    tk.Entry(rules, textvariable=old_var, width=14).grid(row=1, column=1, pady=(4, 0))
    tk.Label(rules, text="→", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=1, column=2)
    tk.Entry(rules, textvariable=new_var, width=14).grid(row=1, column=3, pady=(4, 0))

    # 预览 / 执行
    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(fill="x", padx=14, pady=(6, 4))
    tk.Button(btn_row, text="预览", command=lambda: preview(), font=("Microsoft YaHei UI", 10),
              bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=12,
              cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="执行重命名", command=lambda: apply_rename(), font=("Microsoft YaHei UI", 10),
              bg="#27ae60", fg="#ffffff", relief="flat", padx=12,
              cursor="hand2").pack(side="left", padx=(10, 0))

    # 预览列表
    listbox = tk.Listbox(win, font=("Consolas", 9), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 14), pady=(0, 10))
    listbox.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 10))

    def browse():
        d = filedialog.askdirectory(title="选择要重命名的文件所在目录")
        if d:
            dir_var.set(d)
            preview()

    def preview():
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showwarning("批量重命名", "请先选择有效的目录。")
            return
        plan = _build_rename_plan(directory, prefix_var.get(), suffix_var.get(),
                                  old_var.get(), new_var.get())
        listbox.delete(0, "end")
        if not plan:
            listbox.insert("end", "（没有需要重命名的文件）")
        for old_name, new_name in plan:
            listbox.insert("end", f"{old_name}  →  {new_name}")

    def apply_rename():
        directory = dir_var.get().strip()
        if not directory or not os.path.isdir(directory):
            messagebox.showwarning("批量重命名", "请先选择有效的目录。")
            return
        plan = _build_rename_plan(directory, prefix_var.get(), suffix_var.get(),
                                  old_var.get(), new_var.get())
        if not plan:
            messagebox.showinfo("批量重命名", "没有需要重命名的文件。")
            return
        if not messagebox.askyesno("批量重命名", f"确定对 {len(plan)} 个文件执行重命名吗？"):
            return
        ok = fail = 0
        for old_name, new_name in plan:
            src = os.path.join(directory, old_name)
            dst = os.path.join(directory, new_name)
            try:
                if os.path.exists(dst):
                    fail += 1
                    continue
                os.rename(src, dst)
                ok += 1
            except OSError:
                fail += 1
        preview()
        messagebox.showinfo("批量重命名", f"完成：成功 {ok} 个，失败 {fail} 个。")


# ----------------------------------------------------------------------
# 8. MD5 校验
# ----------------------------------------------------------------------
def _file_hashes(path, chunk_size=1024 * 1024):
    """计算文件 MD5 与 SHA-256，返回 (md5_hex, sha256_hex)。"""
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            md5.update(data)
            sha.update(data)
    return md5.hexdigest(), sha.hexdigest()


def md5_checker(parent):
    """MD5 / SHA-256 校验工具。"""
    win = _open_tool_window(parent, "MD5 校验", 600, 320)
    win.resizable(False, False)
    file_var = tk.StringVar()
    expected_var = tk.StringVar()
    md5_var = tk.StringVar(value="--")
    sha_var = tk.StringVar(value="--")
    compare_var = tk.StringVar(value="")

    # 文件选择
    row0 = tk.Frame(win, bg=_BG)
    row0.pack(fill="x", padx=14, pady=(14, 4))
    tk.Label(row0, text="文件：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row0, textvariable=file_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row0, text="浏览…", command=lambda: browse(), font=("Microsoft YaHei UI", 10),
              bg="#aab4c4", relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(6, 0))

    # 计算按钮
    tk.Button(win, text="计算哈希值", command=lambda: compute(), font=("Microsoft YaHei UI", 11),
              bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=16, pady=4,
              cursor="hand2").pack(pady=(6, 8))

    # 结果显示
    tk.Label(win, text="MD5：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=14)
    tk.Label(win, textvariable=md5_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="w", relief="solid", bd=1).pack(fill="x", padx=14, pady=(0, 6))
    tk.Label(win, text="SHA-256：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=14)
    tk.Label(win, textvariable=sha_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="w", relief="solid", bd=1).pack(fill="x", padx=14, pady=(0, 8))

    # 与预期值比对
    row1 = tk.Frame(win, bg=_BG)
    row1.pack(fill="x", padx=14)
    tk.Label(row1, text="预期 MD5：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row1, textvariable=expected_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row1, text="校验", command=lambda: compare(), font=("Microsoft YaHei UI", 10),
              bg="#27ae60", fg="#ffffff", relief="flat", padx=10,
              cursor="hand2").pack(side="left", padx=(6, 0))
    tk.Label(win, textvariable=compare_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=14, pady=(4, 10))

    def browse():
        path = filedialog.askopenfilename(title="选择要校验的文件")
        if path:
            file_var.set(path)

    def compute():
        path = file_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("MD5 校验", "请先选择有效的文件。")
            return
        md5_var.set("计算中……")
        sha_var.set("")
        compare_var.set("")
        _run_in_thread(win, lambda: _file_hashes(path), on_done)

    def on_done(kind, payload):
        if kind == "error":
            md5_var.set("计算失败")
            messagebox.showerror("MD5 校验", f"计算失败：{payload}")
            return
        md5_hex, sha_hex = payload
        md5_var.set(md5_hex)
        sha_var.set(sha_hex)

    def compare():
        expected = expected_var.get().strip().lower()
        current = md5_var.get().strip().lower()
        if not expected:
            messagebox.showwarning("MD5 校验", "请输入预期 MD5 值。")
            return
        if current in ("--", "计算中……", "计算失败"):
            messagebox.showwarning("MD5 校验", "请先计算文件的 MD5。")
            return
        if expected == current:
            compare_var.set("✓ 校验一致")
        else:
            compare_var.set("✗ 校验不一致！")


# ----------------------------------------------------------------------
# 9. 创建系统还原点
# ----------------------------------------------------------------------
def _create_restore_point(description):
    """创建系统还原点，返回 (ok: bool, message: str)。"""
    safe_desc = description.replace("'", "''")
    cmd = ["powershell", "-NoProfile", "-Command",
           f"Checkpoint-Computer -Description '{safe_desc}' -RestorePointType 'MODIFY_SETTINGS'"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            return True, out or "还原点创建成功"
        return False, out or f"创建失败（返回码 {proc.returncode}）"
    except subprocess.TimeoutExpired:
        return False, "创建超时（系统还原可能较慢或已禁用）"
    except FileNotFoundError:
        return False, "未找到 PowerShell（需要 Windows PowerShell）"
    except Exception as exc:
        return False, f"创建失败：{exc}"


def restore_point(parent):
    """创建系统还原点（不可用时给出提示）。"""
    win = _open_tool_window(parent, "创建系统还原点", 460, 240)
    win.resizable(False, False)
    desc_var = tk.StringVar(value="PCM 还原点")
    status_var = tk.StringVar(value="就绪")

    tk.Label(win, text="创建系统还原点", font=("Microsoft YaHei UI", 13, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(16, 6))
    row = tk.Frame(win, bg=_BG)
    row.pack(fill="x", padx=18, pady=(0, 8))
    tk.Label(row, text="描述：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row, textvariable=desc_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)

    btn = tk.Button(win, text="创建还原点", command=lambda: create(),
                    font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
                    relief="flat", padx=16, pady=4, cursor="hand2")
    btn.pack(pady=(4, 8))

    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_TITLE_FG, wraplength=420, justify="left").pack(padx=18, pady=(0, 4))
    tk.Label(win, text="提示：需要管理员权限，且系统还原功能必须已启用（若不可用会提示）",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 10))

    def create():
        desc = desc_var.get().strip() or "PCM 还原点"
        btn.config(state="disabled")
        status_var.set("正在创建，请稍候……（可能需要 1~2 分钟）")
        _run_in_thread(win, lambda: _create_restore_point(desc), on_done)

    def on_done(kind, payload):
        btn.config(state="normal")
        if kind == "error":
            status_var.set(f"创建失败：{payload}")
            messagebox.showerror("还原点", f"创建失败：{payload}")
            return
        ok, message = payload
        status_var.set(message)
        if ok:
            messagebox.showinfo("还原点", "系统还原点创建成功。")
        else:
            messagebox.showerror("还原点",
                                 "创建失败。\n可能原因：未以管理员身份运行、"
                                 "系统还原功能未启用或磁盘保护未开启。")


# ----------------------------------------------------------------------
# 10. 开机启动项管理
# ----------------------------------------------------------------------
def _hive(name):
    return winreg.HKEY_CURRENT_USER if name == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def _read_run_items():
    """读取注册表 Run 键，返回 [(名称, 命令, 位置), ...]。"""
    items = []
    for hive_name, key_path in RUN_KEYS.items():
        try:
            with winreg.OpenKey(_hive(hive_name), key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append((name, value, hive_name))
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    return items


def _delete_run_item(hive_name, name):
    """删除指定启动项；无权限时抛 PermissionError。"""
    with winreg.OpenKey(_hive(hive_name), RUN_KEYS[hive_name], 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, name)


def _add_run_item(hive_name, name, command):
    """新增启动项；无权限时抛 PermissionError。"""
    with winreg.OpenKey(_hive(hive_name), RUN_KEYS[hive_name], 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)


def startup_manager(parent):
    """开机启动项管理工具。"""
    win = _open_tool_window(parent, "开机启动项管理", 660, 480)

    tree = ttk.Treeview(win, columns=("name", "command", "hive"), show="headings")
    tree.heading("name", text="名称")
    tree.heading("command", text="命令")
    tree.heading("hive", text="位置")
    tree.column("name", width=140)
    tree.column("command", width=380)
    tree.column("hive", width=60, anchor="center")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))

    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(btn_row, text="刷新", command=lambda: refresh(), font=("Microsoft YaHei UI", 10),
              bg=_BTN_BG, fg=_BTN_FG, relief="flat", padx=12,
              cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="删除选中项", command=lambda: delete_selected(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))

    # 新增区
    add_frame = tk.LabelFrame(win, text="新增启动项", font=("Microsoft YaHei UI", 10),
                              bg=_BG, fg=_TITLE_FG, padx=8, pady=6)
    add_frame.pack(fill="x", padx=12, pady=(4, 4))
    name_var = tk.StringVar()
    cmd_var = tk.StringVar()
    hive_var = tk.StringVar(value="HKCU")
    tk.Label(add_frame, text="名称：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=0, sticky="w")
    tk.Entry(add_frame, textvariable=name_var, width=20).grid(row=0, column=1, padx=(0, 10))
    tk.Label(add_frame, text="命令：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=2, sticky="w")
    tk.Entry(add_frame, textvariable=cmd_var, width=30).grid(row=0, column=3)
    tk.Radiobutton(add_frame, text="当前用户 (HKCU)", variable=hive_var, value="HKCU",
                   bg=_BG, font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
    tk.Radiobutton(add_frame, text="所有用户 (HKLM，需管理员)", variable=hive_var, value="HKLM",
                   bg=_BG, font=("Microsoft YaHei UI", 9)).grid(row=1, column=2, columnspan=2, sticky="w", pady=(4, 0))
    tk.Button(add_frame, text="添加", command=lambda: add_item(), font=("Microsoft YaHei UI", 10),
              bg="#27ae60", fg="#ffffff", relief="flat", padx=12,
              cursor="hand2").grid(row=2, column=3, sticky="e", pady=(6, 0))

    tk.Label(win, text="提示：HKLM（所有用户）启动项需要管理员权限",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def refresh():
        tree.delete(*tree.get_children())
        for name, command, hive in _read_run_items():
            tree.insert("", "end", values=(name, command, hive))

    def delete_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("启动项管理", "请先在列表中选择一个启动项。")
            return
        values = tree.item(sel[0], "values")
        name, hive = values[0], values[2]
        if not messagebox.askyesno("启动项管理", f"确定删除启动项“{name}”吗？"):
            return
        try:
            _delete_run_item(hive, name)
            refresh()
        except PermissionError:
            messagebox.showerror("启动项管理",
                                 "删除失败：需要管理员权限。\n请以管理员身份运行 PCM。")
        except OSError as exc:
            messagebox.showerror("启动项管理", f"删除失败：{exc}")

    def add_item():
        name = name_var.get().strip()
        command = cmd_var.get().strip()
        if not name or not command:
            messagebox.showwarning("启动项管理", "请填写名称与命令。")
            return
        try:
            _add_run_item(hive_var.get(), name, command)
            refresh()
            name_var.set("")
            cmd_var.set("")
            messagebox.showinfo("启动项管理", f"已添加启动项“{name}”。")
        except PermissionError:
            messagebox.showerror("启动项管理",
                                 "添加失败：HKLM 需要管理员权限。\n请以管理员身份运行 PCM。")
        except OSError as exc:
            messagebox.showerror("启动项管理", f"添加失败：{exc}")

    refresh()
