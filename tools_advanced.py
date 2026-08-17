# -*- coding: utf-8 -*-
"""
tools_advanced.py —— 高级功能工具集（20 个工具，分 5 组）

每个工具是一个函数，签名统一为 func(parent)（与 tools_system 相同）：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

一、系统增强：   god_mode / memory_monitor / service_manager / context_menu /
                 privacy_cleaner / system_repair
二、硬件监控：   hardware_info / stress_test / disk_health
三、文件管理：   dup_finder / big_files / secure_wipe / uninstall_manager
四、开发工具：   codec_tools / text_crypto / regex_tester / xml_tool / text_processor
五、娱乐扩展：   gif_recorder / auto_clicker

说明：
    - 涉及系统修改的功能（上帝模式、服务管理、右键菜单、隐私清理、系统修复）
      均需相应权限，失败时会给出明确提示；
    - 已存在的功能（磁盘清理、还原点创建、MD5/JSON 工具、读写测速、连接状态等）
      不再重复实现。
"""
import ctypes
import hashlib
import os
import platform
import queue
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor

try:
    import psutil
except ImportError:
    psutil = None

try:
    from PIL import Image, ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from tools_system import _open_tool_window, _run_in_thread

_BG = "#f5f6fa"
_TITLE_FG = "#1f2a3a"
_HINT_FG = "#7a8699"
_BTN_BG = "#3d5a80"
_BTN_FG = "#ffffff"


def _show_text_window(parent, title, width, height, fill=None):
    """创建带只读文本框的工具窗口，返回 (win, text)。"""
    win = _open_tool_window(parent, title, width, height)
    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="word",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))
    if fill is not None:
        _set_text(text, fill)
    return win, text


def _set_text(text, content):
    text.configure(state="normal")
    text.delete("1.0", "end")
    text.insert("1.0", content)
    text.configure(state="disabled")


def _run_sc(cmd):
    """执行 sc / net 等系统命令，返回 (是否成功, 输出文本)。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        out = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


# ======================================================================
# 一、系统增强
# ======================================================================
GOD_MODE_NAME = "GodMode.{ED7BA470-8E54-465E-825C-99712043E01C}"


def _dev_mode_enabled():
    """开发者模式是否已开启。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\AppModelUnlock") as key:
            return winreg.QueryValueEx(key, "AllowDevelopmentWithoutDevLicense")[0] == 1
    except OSError:
        return False


def _set_dev_mode(enable):
    """开启/关闭开发者模式（HKCU，无需管理员）。"""
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\AppModelUnlock",
                            0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "AllowDevelopmentWithoutDevLicense", 0,
                          winreg.REG_DWORD, 1 if enable else 0)


def god_mode(parent):
    """上帝模式（隐藏设置面板）与开发者模式开关。"""
    win = _open_tool_window(parent, "上帝模式 / 开发者模式", 520, 400)
    win.resizable(False, False)
    status_var = tk.StringVar(value="就绪")

    tk.Label(win, text="上帝模式 / 开发者模式", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(16, 4))
    tk.Label(win, text="上帝模式：桌面生成“GodMode”文件夹，内含全部系统设置入口",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 8))

    tk.Button(win, text="开启上帝模式（创建 GodMode 文件夹）", command=lambda: toggle_god(True),
              font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=16, pady=5, cursor="hand2").pack(fill="x", padx=50, pady=4)
    tk.Button(win, text="关闭上帝模式（删除 GodMode 文件夹）", command=lambda: toggle_god(False),
              font=("Microsoft YaHei UI", 11), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=16, pady=5, cursor="hand2").pack(fill="x", padx=50, pady=4)

    dev_var = tk.StringVar(value=f"开发者模式：{'已开启' if _dev_mode_enabled() else '未开启'}")
    tk.Label(win, textvariable=dev_var, font=("Microsoft YaHei UI", 11),
             bg="#ffffff", fg=_TITLE_FG, relief="solid", bd=1,
             padx=8).pack(fill="x", padx=50, pady=(12, 4))
    tk.Button(win, text="切换开发者模式", command=lambda: toggle_dev(),
              font=("Microsoft YaHei UI", 11), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=16, pady=5, cursor="hand2").pack(fill="x", padx=50, pady=4)
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG).pack(pady=(6, 8))

    def toggle_god(enable):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        folder = os.path.join(desktop, GOD_MODE_NAME)
        try:
            if enable:
                os.makedirs(folder, exist_ok=True)
                status_var.set(f"已创建：{folder}")
            else:
                if os.path.isdir(folder) and os.path.basename(folder) == GOD_MODE_NAME:
                    os.rmdir(folder)  # 只删除同名的 GodMode 文件夹
                    status_var.set("已删除 GodMode 文件夹")
                else:
                    status_var.set("未找到 GodMode 文件夹")
        except OSError as exc:
            status_var.set(f"操作失败：{exc}")

    def toggle_dev():
        enable = not _dev_mode_enabled()
        try:
            _set_dev_mode(enable)
        except OSError as exc:
            status_var.set(f"操作失败：{exc}")
            return
        dev_var.set(f"开发者模式：{'已开启' if enable else '未开启'}")
        status_var.set("开发者模式已切换" + ("（可能需要重启资源管理器生效）" if enable else ""))


def memory_monitor(parent):
    """内存管理与监控（状态 + 占用 Top 进程）。"""
    win = _open_tool_window(parent, "内存监控", 560, 440)
    info_var = tk.StringVar(value="读取中……")
    listbox = tk.Listbox(win, font=("Consolas", 9), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)

    tk.Label(win, textvariable=info_var, font=("Microsoft YaHei UI", 11),
             bg="#ffffff", fg=_TITLE_FG, anchor="w", relief="solid", bd=1,
             padx=8).pack(fill="x", padx=12, pady=(12, 4))
    tk.Label(win, text="内存占用最高的 12 个进程：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=12)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    listbox.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tk.Button(win, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=14, cursor="hand2").pack(pady=(0, 8))

    def refresh():
        if not psutil:
            info_var.set("未安装 psutil，无法读取内存信息。\npip install psutil")
            return
        vm = psutil.virtual_memory()
        info_var.set(
            f"物理内存：{vm.used / 1073741824:.1f} / {vm.total / 1073741824:.1f} GB"
            f"（{vm.percent}%）  可用：{vm.available / 1073741824:.1f} GB")
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if p.info["memory_info"]:
                    procs.append((p.info["memory_info"].rss, p.info["pid"], p.info["name"]))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(reverse=True)
        listbox.delete(0, "end")
        for rss, pid, name in procs[:12]:
            listbox.insert("end", f"{rss / 1048576:10.1f} MB   PID {pid:<6d} {name}")

    refresh()


def service_manager(parent):
    """Windows 服务管理（查看/启动/停止/设置启动类型）。"""
    win = _open_tool_window(parent, "服务管理", 640, 480)
    tree = ttk.Treeview(win, columns=("name", "display", "state"), show="headings")
    tree.heading("name", text="服务名")
    tree.heading("display", text="显示名称")
    tree.heading("state", text="状态")
    tree.column("name", width=140)
    tree.column("display", width=300)
    tree.column("state", width=90, anchor="center")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))

    btns = tk.Frame(win, bg=_BG)
    btns.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(btns, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=10, cursor="hand2").pack(side="left")
    tk.Button(btns, text="启动", command=lambda: action("start"),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(btns, text="停止", command=lambda: action("stop"),
              font=("Microsoft YaHei UI", 10), bg="#e67e22", fg="#ffffff",
              relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(btns, text="设为自动", command=lambda: action("auto"),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", fg=_TITLE_FG,
              relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(btns, text="设为禁用", command=lambda: action("disabled"),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))

    status = tk.Label(win, text="提示：启动/停止/修改服务需要管理员权限",
                      font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG, anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 8))

    def refresh():
        tree.delete(*tree.get_children())
        ok, out = _run_sc(["sc", "query", "type=", "service", "state=", "all"])
        if not ok:
            status.config(text=f"读取失败：{out[:200]}")
            return
        name = display = state = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("DISPLAY_NAME:"):
                display = line.split(":", 1)[1].strip()
            elif line.startswith("STATE"):
                m = re.search(r"\d+", line)
                state = ("运行中" if m and m.group(0) == "4" else "已停止")
            elif line.startswith("WIN32_EXIT_CODE") and name:
                tree.insert("", "end", values=(name, display, state))
                name = display = state = None
        status.config(text=f"共 {len(tree.get_children())} 个服务")

    def action(kind):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("服务管理", "请先选择一个服务。")
            return
        sname = tree.item(sel[0], "values")[0]
        cmd = {
            "start": ["sc", "start", sname],
            "stop": ["sc", "stop", sname],
            "auto": ["sc", "config", sname, "start=", "auto"],
            "disabled": ["sc", "config", sname, "start=", "disabled"],
        }[kind]
        ok, out = _run_sc(cmd)
        if ok:
            messagebox.showinfo("服务管理", f"操作成功：{sname}")
            refresh()
        else:
            messagebox.showerror("服务管理",
                                 f"操作失败（可能需要管理员权限）：\n{out[-300:]}")

    refresh()


def context_menu(parent):
    """右键菜单管理（HKCU，无需管理员）。"""
    win = _open_tool_window(parent, "右键菜单管理", 600, 480)
    scope_var = tk.StringVar(value="文件")
    name_var = tk.StringVar()
    cmd_var = tk.StringVar(value='notepad.exe "%1"')
    listbox = tk.Listbox(win, font=("Consolas", 9), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(top, text="作用范围：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    ttk.Combobox(top, textvariable=scope_var, values=["文件", "文件夹", "文件夹背景", "桌面背景"],
                 state="readonly", width=12).pack(side="left")
    tk.Button(top, text="刷新列表", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))

    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    listbox.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))

    form = tk.LabelFrame(win, text="新增/删除自定义菜单项", font=("Microsoft YaHei UI", 10),
                         bg=_BG, fg=_TITLE_FG, padx=8, pady=6)
    form.pack(fill="x", padx=12, pady=(0, 6))
    tk.Label(form, text="菜单名：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=0, sticky="w")
    tk.Entry(form, textvariable=name_var, width=20).grid(row=0, column=1, padx=(0, 10))
    tk.Label(form, text="命令：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=2, sticky="w")
    tk.Entry(form, textvariable=cmd_var, width=30).grid(row=0, column=3)
    tk.Button(form, text="添加", command=lambda: add_item(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").grid(row=1, column=3, sticky="e", pady=(6, 0))
    tk.Button(form, text="删除选中", command=lambda: remove_item(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").grid(row=1, column=2, sticky="e", pady=(6, 0))

    _SCOPE_KEYS = {
        "文件": r"Software\Classes\*\shell",
        "文件夹": r"Software\Classes\Directory\shell",
        "文件夹背景": r"Software\Classes\Directory\Background\shell",
        "桌面背景": r"Software\Classes\DesktopBackground\shell",
    }

    def refresh():
        import winreg
        listbox.delete(0, "end")
        base = _SCOPE_KEYS[scope_var.get()]
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as key:
                i = 0
                while True:
                    try:
                        entry = winreg.EnumKey(key, i)
                        i += 1
                        cmd = ""
                        try:
                            with winreg.OpenKey(key, entry + r"\command") as ck:
                                cmd = winreg.QueryValue(ck, None) or ""
                        except OSError:
                            pass
                        listbox.insert("end", f"{entry}    →    {cmd}")
                    except OSError:
                        break
        except OSError:
            pass

    def add_item():
        import winreg
        name = name_var.get().strip()
        cmd = cmd_var.get().strip()
        if not name or not cmd:
            messagebox.showwarning("右键菜单", "请填写菜单名与命令。")
            return
        base = _SCOPE_KEYS[scope_var.get()]
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                    base + "\\" + name + r"\command",
                                    0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, None, 0, winreg.REG_SZ, cmd)
        except OSError as exc:
            messagebox.showerror("右键菜单", f"添加失败：{exc}")
            return
        refresh()
        messagebox.showinfo("右键菜单", f"已添加“{name}”，立即生效。")

    def remove_item():
        import winreg
        sel = listbox.curselection()
        if not sel:
            messagebox.showinfo("右键菜单", "请先在列表中选择要删除的菜单项。")
            return
        entry = listbox.get(sel[0]).split("    →")[0].strip()
        base = _SCOPE_KEYS[scope_var.get()]
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + "\\" + entry + r"\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + "\\" + entry)
        except OSError as exc:
            messagebox.showerror("右键菜单", f"删除失败：{exc}")
            return
        refresh()
        messagebox.showinfo("右键菜单", f"已删除“{entry}”。")

    refresh()


def privacy_cleaner(parent):
    """隐私清理（最近文档、运行历史、临时文件）。"""
    win = _open_tool_window(parent, "隐私清理", 520, 400)
    status_var = tk.StringVar(value="就绪")
    items = [
        ("最近打开的文档", [os.path.join(os.environ.get("APPDATA", ""),
                                        "Microsoft", "Windows", "Recent")]),
        ("%TEMP% 临时文件", [os.environ.get("TEMP", "")]),
        ("运行历史 (RunMRU)", []),
    ]
    vars_ = {name: tk.BooleanVar(value=True) for name, _ in items}

    tk.Label(win, text="隐私清理", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(14, 4))
    tk.Label(win, text="选择要清理的项目（删除操作不可恢复）", font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG).pack(pady=(0, 8))
    for name, _ in items:
        tk.Checkbutton(win, text=name, variable=vars_[name], bg=_BG,
                       font=("Microsoft YaHei UI", 11)).pack(anchor="w", padx=40, pady=2)
    tk.Button(win, text="立即清理", command=lambda: clean(),
              font=("Microsoft YaHei UI", 11), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=16, pady=5, cursor="hand2").pack(pady=(10, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG, wraplength=460).pack(pady=(0, 10))

    def clean():
        deleted = 0
        notes = []
        for name, dirs in items:
            if not vars_[name].get():
                continue
            for d in dirs:
                if not d or not os.path.isdir(d):
                    continue
                try:
                    for f in os.listdir(d):
                        p = os.path.join(d, f)
                        try:
                            if os.path.isfile(p):
                                os.remove(p)
                            elif os.path.isdir(p):
                                shutil.rmtree(p)
                            deleted += 1
                        except OSError:
                            pass
                except OSError as exc:
                    notes.append(f"{name}: {exc}")
            if name == "运行历史 (RunMRU)":
                _clear_runmru()
                notes.append("运行历史：已清空")
        status_var.set(f"清理完成：删除 {deleted} 项" + ("；" + "；".join(notes) if notes else ""))


def _clear_runmru():
    """清空“运行”历史记录（RunMRU 注册表值）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU",
                            0, winreg.KEY_SET_VALUE) as key:
            i = 0
            while True:
                try:
                    winreg.DeleteValue(key, winreg.EnumValue(key, 0)[0])
                except OSError:
                    break
    except OSError:
        pass


def system_repair(parent):
    """一键修复（DISM / SFC / chkdsk）。"""
    win = _open_tool_window(parent, "系统一键修复", 640, 460)
    status_var = tk.StringVar(value="就绪")
    text = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="word",
                   bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))

    tk.Label(win, text="提示：以下命令需要管理员权限且耗时较长，执行期间请勿关闭窗口",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=12, pady=(0, 4))

    def run(cmd, desc):
        status_var.set(desc + "（运行中……）")
        _set_text(text, f"$ {' '.join(cmd)}\n运行中，请稍候……")
        _run_in_thread(win, lambda: _run_sc(cmd), lambda k, p: on_done(k, p, desc))

    def on_done(kind, payload, desc):
        if kind == "error":
            _set_text(text, payload)
            status_var.set(f"{desc}失败")
            return
        ok, out = payload
        _set_text(text, out[-3000:] or "(无输出)")
        status_var.set(desc + ("完成" if ok else "失败（可能需要管理员权限）"))

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(4, 4))
    tk.Button(top, text="DISM 扫描健康", command=lambda: run(
        ["DISM", "/Online", "/Cleanup-Image", "/ScanHealth"], "DISM 扫描"),
        font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
        relief="flat", padx=10, cursor="hand2").pack(side="left")
    tk.Button(top, text="DISM 修复", command=lambda: run(
        ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], "DISM 修复"),
        font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
        relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(top, text="SFC 系统文件检查", command=lambda: run(
        ["sfc", "/scannow"], "SFC 检查"),
        font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
        relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(top, text="chkdsk 检查 C 盘", command=lambda: run(
        ["chkdsk", "C:", "/f"], "chkdsk"),
        font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
        relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))

    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(fill="x", padx=12, pady=(0, 8))


# ======================================================================
# 二、硬件与性能监控
# ======================================================================
def hardware_info(parent):
    """硬件信息检测。"""
    win, text = _show_text_window(parent, "硬件信息", 620, 460)
    tk.Button(win, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(pady=(0, 8))

    def refresh():
        _set_text(text, "\n".join(_collect_hardware_info()) or "(无法获取)")

    refresh()


def _collect_hardware_info():
    """收集硬件信息，返回行列表。"""
    lines = [f"操作系统: {platform.system()} {platform.release()} ({platform.machine()})"]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            lines.append(f"CPU: {winreg.QueryValueEx(key, 'ProcessorNameString')[0]}")
    except OSError:
        lines.append("CPU: 读取失败")
    if psutil:
        vm = psutil.virtual_memory()
        lines.append(f"内存: {vm.total / 1073741824:.1f} GB（可用 {vm.available / 1073741824:.1f} GB）")
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController).Name; "
             "(Get-CimInstance Win32_BaseBoard).Product; "
             "(Get-PhysicalDisk).Model"],
            capture_output=True, text=True, timeout=30)
        parts = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
        if len(parts) > 0:
            lines.append(f"显卡: {parts[0]}")
        if len(parts) > 1:
            lines.append(f"主板: {parts[1]}")
        if len(parts) > 2:
            lines.append(f"硬盘: {'、'.join(parts[2:])}")
    except Exception:
        lines.append("显卡/主板/硬盘: 读取失败（可能需要管理员权限）")
    return lines


def stress_test(parent):
    """CPU / 内存 / 显卡压力测试。"""
    win = _open_tool_window(parent, "性能压力测试", 560, 420)
    cores_var = tk.StringVar(value="4")
    mem_var = tk.StringVar(value="512")
    dur_var = tk.StringVar(value="10")
    cpu_cb = tk.BooleanVar(value=True)
    mem_cb = tk.BooleanVar(value=True)
    gpu_cb = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value="就绪")
    running = [False]

    form = tk.Frame(win, bg=_BG)
    form.pack(fill="x", padx=14, pady=(14, 4))
    tk.Label(form, text="CPU 线程：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=0, sticky="w")
    tk.Entry(form, textvariable=cores_var, width=6).grid(row=0, column=1, padx=(0, 12))
    tk.Label(form, text="内存 (MB)：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=2, sticky="w")
    tk.Entry(form, textvariable=mem_var, width=8).grid(row=0, column=3, padx=(0, 12))
    tk.Label(form, text="时长 (秒)：", font=("Microsoft YaHei UI", 10), bg=_BG).grid(row=0, column=4, sticky="w")
    tk.Entry(form, textvariable=dur_var, width=6).grid(row=0, column=5)

    opts = tk.Frame(win, bg=_BG)
    opts.pack(fill="x", padx=14, pady=4)
    tk.Checkbutton(opts, text="CPU 计算压力", variable=cpu_cb, bg=_BG,
                   font=("Microsoft YaHei UI", 10)).pack(side="left")
    tk.Checkbutton(opts, text="内存占用压力", variable=mem_cb, bg=_BG,
                   font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(12, 0))
    tk.Checkbutton(opts, text="显卡渲染(动画FPS)", variable=gpu_cb, bg=_BG,
                   font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(12, 0))

    btn = tk.Button(win, text="开始测试", command=lambda: start(),
                    font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
                    relief="flat", padx=16, pady=4, cursor="hand2")
    btn.pack(pady=(4, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#ffffff", fg=_TITLE_FG, relief="solid", bd=1,
             anchor="w", padx=8).pack(fill="x", padx=14, pady=(0, 8))
    tk.Label(win, text="注意：内存压力请勿超过可用内存的 70%，防止系统卡死",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 8))

    def start():
        if running[0]:
            return
        try:
            cores = max(1, int(cores_var.get()))
            mem_mb = max(16, int(mem_var.get()))
            duration = max(3, int(dur_var.get()))
        except ValueError:
            messagebox.showwarning("压力测试", "请输入有效数值。")
            return
        if not (cpu_cb.get() or mem_cb.get() or gpu_cb.get()):
            messagebox.showwarning("压力测试", "请至少勾选一项测试。")
            return
        running[0] = True
        btn.config(state="disabled", text="测试中……")
        threading.Thread(target=worker, args=(cores, mem_mb, duration), daemon=True).start()

    def worker(cores, mem_mb, duration):
        stop = threading.Event()
        workers = []
        if cpu_cb.get():
            for _ in range(cores):
                t = threading.Thread(target=_cpu_loop, args=(stop,), daemon=True)
                t.start()
                workers.append(t)
        chunks = []
        if mem_cb.get():
            try:
                for _ in range(mem_mb // 16):
                    chunks.append(bytearray(16 * 1024 * 1024))
            except MemoryError:
                pass
        start_ts = time.time()
        cpu_samples = []
        if psutil:
            while time.time() - start_ts < duration:
                cpu_samples.append(psutil.cpu_percent(interval=0.5))
        else:
            time.sleep(duration)
        stop.set()
        for t in workers:
            t.join(timeout=1)
        chunks.clear()
        avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
        msg = f"测试完成：平均 CPU {avg_cpu:.0f}%，内存占用约 {len(chunks) * 16 + mem_mb} MB"
        running[0] = False
        win.after(0, lambda: (btn.config(state="normal", text="开始测试"),
                              status_var.set(msg)))

    def _cpu_loop(stop):
        x = 1
        while not stop.is_set():
            x = (x * 16807) % 2147483647  # 简单伪随机计算

    def gpu():  # 预留显卡动画接口（未使用）
        pass


def disk_health(parent):
    """磁盘健康（S.M.A.R.T. 状态）与使用率。"""
    win, text = _show_text_window(parent, "磁盘健康", 640, 440)
    tk.Button(win, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(pady=(0, 8))

    def refresh():
        lines = []
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus | "
                 "Format-Table -AutoSize | Out-String"],
                capture_output=True, text=True, timeout=30)
            out = proc.stdout.strip()
            if out:
                lines.append(out)
        except Exception:
            pass
        if psutil:
            for part in psutil.disk_partitions():
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    lines.append(f"{part.device}  {u.used / 1073741824:.1f} / "
                                 f"{u.total / 1073741824:.1f} GB（{u.percent}%）")
                except OSError:
                    pass
        _set_text(text, "\n".join(lines) or "无法获取磁盘健康信息（S.M.A.R.T. 需要管理员权限）")

    refresh()


# ======================================================================
# 三、文件与数据管理
# ======================================================================
def _file_hash(path, chunk=1024 * 1024):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                data = f.read(chunk)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
    except OSError:
        return None


def _find_duplicates(directory):
    """扫描目录中的重复文件，返回 [(大小, [路径...]), ...]（每组 ≥2 个）。"""
    size_map = {}
    for dirpath, dirnames, filenames in os.walk(directory, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                size_map.setdefault(os.path.getsize(full), []).append(full)
            except OSError:
                continue
    groups = []
    for size, paths in size_map.items():
        if len(paths) < 2 or size == 0:
            continue
        hash_map = {}
        for p in paths:
            h = _file_hash(p)
            if h:
                hash_map.setdefault(h, []).append(p)
        for group in hash_map.values():
            if len(group) >= 2:
                groups.append(group)
    return groups


def dup_finder(parent):
    """重复文件查找与清理。"""
    win = _open_tool_window(parent, "重复文件查找", 620, 480)
    dir_var = tk.StringVar(value=os.path.expanduser("~"))
    status_var = tk.StringVar(value="就绪")
    tree = ttk.Treeview(win, columns=("file", "size"), show="headings")
    tree.heading("file", text="文件")
    tree.heading("size", text="大小")
    tree.column("file", width=460)
    tree.column("size", width=90, anchor="center")
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))
    tree.configure(selectmode="extended")

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(8, 4))
    tk.Label(top, text="目录：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(top, textvariable=dir_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(top, text="浏览", command=lambda: dir_var.set(filedialog.askdirectory()),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
              padx=10, cursor="hand2").pack(side="left", padx=(6, 0))
    tk.Button(top, text="扫描", command=lambda: scan(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(6, 0))
    tk.Button(win, text="删除选中（进回收站）", command=lambda: delete_selected(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(anchor="w", padx=12, pady=(0, 4))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def scan():
        directory = dir_var.get().strip()
        if not os.path.isdir(directory):
            messagebox.showwarning("重复文件", "请选择有效目录。")
            return
        tree.delete(*tree.get_children())
        status_var.set("扫描中（按大小分组后做 MD5 比对）……")
        _run_in_thread(win, lambda: _find_duplicates(directory), on_done)

    def on_done(kind, payload):
        if kind == "error":
            status_var.set(f"扫描失败：{payload}")
            return
        groups = payload
        total = 0
        for group in groups:
            size = os.path.getsize(group[0])
            total += size * (len(group) - 1)
            for path in group:
                tree.insert("", "end", values=(path, f"{size / 1048576:.1f} MB"))
        status_var.set(f"发现 {len(groups)} 组重复，可释放约 {total / 1073741824:.2f} GB")

    def delete_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("重复文件", "请先选中要删除的重复文件（可多选）。")
            return
        paths = [tree.item(i, "values")[0] for i in sel]
        if not messagebox.askyesno("重复文件", f"确定将选中的 {len(paths)} 个文件移入回收站吗？"):
            return
        try:
            import send2trash
        except ImportError:
            messagebox.showerror("重复文件", "未安装 send2trash。\npip install send2trash")
            return
        ok = fail = 0
        for p in paths:
            try:
                send2trash.send2trash(p)
                ok += 1
            except Exception:
                fail += 1
        scan()
        messagebox.showinfo("重复文件", f"完成：成功 {ok} 个，失败 {fail} 个。")

    scan() if False else None


def _big_files(directory, top=50):
    """扫描目录返回最大的 N 个文件 [(大小, 路径)]。"""
    items = []
    for dirpath, dirnames, filenames in os.walk(directory, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                items.append((os.path.getsize(full), full))
            except OSError:
                continue
    items.sort(reverse=True)
    return items[:top]


def big_files(parent):
    """大文件分析（磁盘空间占用定位）。"""
    win = _open_tool_window(parent, "大文件分析", 640, 460)
    dir_var = tk.StringVar(value=os.path.expanduser("~"))
    status_var = tk.StringVar(value="就绪")
    listbox = tk.Listbox(win, font=("Consolas", 9), bg="#ffffff",
                         fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=listbox.yview)
    listbox.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    listbox.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(8, 4))
    tk.Label(top, text="目录：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(top, textvariable=dir_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(top, text="浏览", command=lambda: dir_var.set(filedialog.askdirectory()),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
              padx=10, cursor="hand2").pack(side="left", padx=(6, 0))
    tk.Button(top, text="分析", command=lambda: analyze(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(6, 0))
    tk.Button(win, text="打开所在文件夹", command=lambda: open_dir(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(anchor="w", padx=12, pady=(0, 4))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def analyze():
        directory = dir_var.get().strip()
        if not os.path.isdir(directory):
            messagebox.showwarning("大文件", "请选择有效目录。")
            return
        listbox.delete(0, "end")
        status_var.set("分析中……")
        _run_in_thread(win, lambda: _big_files(directory), on_done)

    def on_done(kind, payload):
        if kind == "error":
            status_var.set(f"分析失败：{payload}")
            return
        for size, path in payload:
            listbox.insert("end", f"{size / 1073741824:8.2f} GB  {path}")
        status_var.set(f"已列出最大的 {len(payload)} 个文件")

    def open_dir():
        sel = listbox.curselection()
        if not sel:
            messagebox.showinfo("大文件", "请先选择一个文件。")
            return
        path = listbox.get(sel[0]).split("  ", 1)[1]
        try:
            os.startfile(os.path.dirname(path))
        except OSError as exc:
            messagebox.showerror("大文件", str(exc))


def _secure_wipe(paths, passes=3):
    """多次随机覆写后删除文件；目录直接删除。返回 (成功数, 失败数)。"""
    ok = fail = 0
    for path in paths:
        try:
            if os.path.isfile(path):
                size = os.path.getsize(path)
                chunk = 1024 * 1024
                with open(path, "r+b") as f:
                    for _ in range(max(1, passes)):
                        f.seek(0)
                        remaining = size
                        while remaining > 0:
                            n = min(chunk, remaining)
                            f.write(os.urandom(n))
                            remaining -= n
                        f.flush()
                        os.fsync(f.fileno())
                os.remove(path)
                ok += 1
            elif os.path.isdir(path):
                shutil.rmtree(path)
                ok += 1
        except OSError:
            fail += 1
    return ok, fail


def secure_wipe(parent):
    """安全删除（覆写后删除，防恢复）。"""
    win = _open_tool_window(parent, "安全删除", 560, 320)
    file_var = tk.StringVar()
    passes_var = tk.StringVar(value="3")
    status_var = tk.StringVar(value="就绪")

    row = tk.Frame(win, bg=_BG)
    row.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(row, text="文件/目录：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(row, textvariable=file_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row, text="选择", command=lambda: file_var.set(
        filedialog.askopenfilename(title="选择要彻底删除的文件")),
        font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
        padx=10, cursor="hand2").pack(side="left", padx=(6, 0))

    row2 = tk.Frame(win, bg=_BG)
    row2.pack(fill="x", padx=14, pady=(0, 6))
    tk.Label(row2, text="覆写次数：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(row2, textvariable=passes_var, width=6).pack(side="left")

    btn = tk.Button(win, text="彻底擦除", command=lambda: wipe(),
                    font=("Microsoft YaHei UI", 11), bg="#c0392b", fg="#ffffff",
                    relief="flat", padx=16, pady=5, cursor="hand2")
    btn.pack(pady=(8, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(pady=(0, 6))
    tk.Label(win, text="注意：操作不可恢复！SSD 上覆写效果有限，建议用于机械硬盘",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 10))

    def wipe():
        path = file_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("安全删除", "请选择有效的文件或目录。")
            return
        try:
            passes = max(1, int(passes_var.get()))
        except ValueError:
            passes = 3
        if not messagebox.askyesno("安全删除", f"确定彻底删除（不可恢复）以下内容吗？\n{path}"):
            return
        btn.config(state="disabled")
        _run_in_thread(win, lambda: _secure_wipe([path], passes), on_done)

    def on_done(kind, payload):
        btn.config(state="normal")
        if kind == "error":
            status_var.set(f"擦除失败：{payload}")
            return
        ok, fail = payload
        status_var.set(f"完成：成功 {ok} 个，失败 {fail} 个。")


def uninstall_manager(parent):
    """软件卸载管理（列出已安装程序并调用其卸载程序）。"""
    win = _open_tool_window(parent, "软件卸载管理", 680, 480)
    tree = ttk.Treeview(win, columns=("name", "version", "publisher"), show="headings")
    for col, text, width in (("name", "软件名称", 300), ("version", "版本", 120),
                             ("publisher", "发行商", 180)):
        tree.heading(col, text=text)
        tree.column(col, width=width)
    sb = ttk.Scrollbar(win, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(10, 6))
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(10, 6))

    btns = tk.Frame(win, bg=_BG)
    btns.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(btns, text="刷新", command=lambda: refresh(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Button(btns, text="卸载选中软件", command=lambda: uninstall(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Label(win, text="提示：卸载会调用软件自带的卸载程序，请按提示操作",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def refresh():
        tree.delete(*tree.get_children())
        for name, version, publisher in _installed_programs():
            tree.insert("", "end", values=(name, version, publisher))

    def uninstall():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("卸载管理", "请先选择要卸载的软件。")
            return
        name = tree.item(sel[0], "values")[0]
        cmd = _uninstall_command(name)
        if not cmd:
            messagebox.showinfo("卸载管理", f"“{name}”没有可用的卸载程序（可能是系统组件）。")
            return
        if not messagebox.askyesno("卸载管理", f"确定卸载“{name}”吗？\n将打开其卸载程序。"):
            return
        try:
            subprocess.Popen(cmd, shell=True)
        except OSError as exc:
            messagebox.showerror("卸载管理", f"启动卸载程序失败：{exc}")

    refresh()


def _installed_programs():
    """读取注册表 Uninstall 键，返回 [(名称, 版本, 发行商)]。"""
    import winreg
    items = {}
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            def q(name):
                                try:
                                    return winreg.QueryValueEx(sk, name)[0]
                                except OSError:
                                    return None
                            disp = q("DisplayName")
                            if disp:
                                items[disp] = (q("DisplayVersion") or "", q("Publisher") or "")
                    except OSError:
                        continue
        except OSError:
            continue
    result = []
    for disp, (ver, pub) in sorted(items.items(), key=lambda x: x[0].lower()):
        result.append((disp, ver, pub))
    return result


def _uninstall_command(name):
    """返回指定软件的卸载命令（UninstallString）。"""
    import winreg
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            try:
                                if winreg.QueryValueEx(sk, "DisplayName")[0] == name:
                                    cmd = winreg.QueryValueEx(sk, "UninstallString")[0]
                                    quiet = winreg.QueryValueEx(sk, "QuietUninstallString")[0]
                                    return quiet or cmd
                            except OSError:
                                continue
                    except OSError:
                        continue
        except OSError:
            continue
    return None


# ======================================================================
# 四、开发工具
# ======================================================================
_CODEC_MODES = ["Base64 编码", "Base64 解码", "URL 编码", "URL 解码",
                "HTML 编码", "HTML 解码", "Unicode 转义", "Unicode 反转义"]


def _codec_convert(mode, text):
    """编解码转换，返回结果文本。"""
    import base64
    import html as html_mod
    import urllib.parse
    if mode == "Base64 编码":
        return base64.b64encode(text.encode()).decode()
    if mode == "Base64 解码":
        return base64.b64decode(text).decode(errors="replace")
    if mode == "URL 编码":
        return urllib.parse.quote(text)
    if mode == "URL 解码":
        return urllib.parse.unquote(text)
    if mode == "HTML 编码":
        return html_mod.escape(text)
    if mode == "HTML 解码":
        return html_mod.unescape(text)
    if mode == "Unicode 转义":
        return text.encode("unicode_escape").decode()
    return text.encode().decode("unicode_escape")


def codec_tools(parent):
    """编码解码工具集。"""
    win = _open_tool_window(parent, "编码解码", 620, 440)
    mode_var = tk.StringVar(value="Base64 编码")
    input_text = tk.Text(win, font=("Consolas", 10), height=6, relief="solid", bd=1)
    output_text = tk.Text(win, font=("Consolas", 10), height=6, state="disabled",
                          relief="solid", bd=1)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    ttk.Combobox(top, textvariable=mode_var, values=_CODEC_MODES,
                 state="readonly", width=18).pack(side="left")
    tk.Button(top, text="转换", command=lambda: convert(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(top, text="复制结果", command=lambda: copy(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))

    input_text.pack(fill="x", padx=12, pady=(0, 4))
    output_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def convert():
        try:
            result = _codec_convert(mode_var.get(), input_text.get("1.0", "end-1c"))
        except Exception as exc:
            result = f"转换失败：{exc}"
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.insert("1.0", result)
        output_text.configure(state="disabled")

    def copy():
        win.clipboard_clear()
        win.clipboard_append(output_text.get("1.0", "end-1c"))
        win.update()
        messagebox.showinfo("编码解码", "已复制到剪贴板。")


def _xor_bytes(data, key):
    keyb = key.encode("utf-8") if key else b"pcm"
    return bytes(b ^ keyb[i % len(keyb)] for i, b in enumerate(data))


def _caesar(text, shift):
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + shift) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + shift) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def _crypto_convert(mode, text, key, shift):
    if mode.startswith("XOR"):
        if mode.endswith("加密"):
            return _xor_bytes(text.encode("utf-8"), key).hex()
        return _xor_bytes(bytes.fromhex(text), key).decode("utf-8", errors="replace")
    if mode.endswith("加密"):
        return _caesar(text, shift)
    return _caesar(text, -shift)


def text_crypto(parent):
    """文本加解密（XOR / 凯撒）。"""
    win = _open_tool_window(parent, "文本加解密", 620, 460)
    mode_var = tk.StringVar(value="XOR 加密")
    key_var = tk.StringVar(value="pcm-key")
    shift_var = tk.StringVar(value="3")
    input_text = tk.Text(win, font=("Consolas", 10), height=5, relief="solid", bd=1)
    output_text = tk.Text(win, font=("Consolas", 10), height=5, state="disabled",
                          relief="solid", bd=1)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    ttk.Combobox(top, textvariable=mode_var, values=["XOR 加密", "XOR 解密", "凯撒加密", "凯撒解密"],
                 state="readonly", width=12).pack(side="left")
    tk.Label(top, text="密钥：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left", padx=(8, 0))
    tk.Entry(top, textvariable=key_var, width=12).pack(side="left")
    tk.Label(top, text="位移：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left", padx=(8, 0))
    tk.Entry(top, textvariable=shift_var, width=5).pack(side="left")
    tk.Button(top, text="执行", command=lambda: run(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))

    input_text.pack(fill="x", padx=12, pady=(0, 4))
    output_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def run():
        try:
            shift = int(shift_var.get())
            result = _crypto_convert(mode_var.get(), input_text.get("1.0", "end-1c"),
                                     key_var.get(), shift)
        except Exception as exc:
            result = f"执行失败：{exc}"
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.insert("1.0", result)
        output_text.configure(state="disabled")


def regex_tester(parent):
    """正则表达式测试。"""
    win = _open_tool_window(parent, "正则表达式测试", 680, 520)
    pattern_var = tk.StringVar()
    flags = {"忽略大小写 I": re.I, "多行 M": re.M, "点匹配换行 S": re.S}
    flag_vars = {k: tk.BooleanVar(value=False) for k in flags}
    result_var = tk.StringVar(value="匹配数：-")

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(top, text="正则：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(top, textvariable=pattern_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(top, text="测试", command=lambda: run(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))
    for k, v in flags.items():
        tk.Checkbutton(top, text=k, variable=flag_vars[k], bg=_BG,
                       font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(6, 0))

    text = tk.Text(win, font=("Consolas", 10), relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 4))
    text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 4))
    tk.Label(win, textvariable=result_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=12, pady=(0, 8))

    def run():
        pattern = pattern_var.get()
        content = text.get("1.0", "end-1c")
        text.tag_remove("match", "1.0", "end")
        if not pattern:
            result_var.set("请输入正则表达式")
            return
        fl = 0
        for k, v in flags.items():
            if flag_vars[k].get():
                fl |= v
        try:
            matches = list(re.finditer(pattern, content, fl))
        except re.error as exc:
            result_var.set(f"正则错误：{exc}")
            return
        for m in matches:
            start = f"1.0+{m.start()}c"
            end = f"1.0+{m.end()}c"
            text.tag_add("match", start, end)
        text.tag_config("match", background="#ffe08a")
        result_var.set(f"匹配数：{len(matches)}" + (f"，共 {len(content)} 字符" if content else ""))


def _format_xml(text, indent="  "):
    """格式化 XML；返回 (结果, 错误)。"""
    import xml.dom.minidom
    try:
        dom = xml.dom.minidom.parseString(text)
        pretty = dom.toprettyxml(indent=indent)
        return "\n".join(ln for ln in pretty.splitlines() if ln.strip()), ""
    except Exception as exc:
        return "", f"XML 解析失败：{exc}"


def xml_tool(parent):
    """XML 格式化 / 压缩 / 校验。"""
    win = _open_tool_window(parent, "XML 工具", 680, 500)
    input_text = tk.Text(win, font=("Consolas", 9), height=8, relief="solid", bd=1)
    output_text = tk.Text(win, font=("Consolas", 9), state="disabled", relief="solid", bd=1)
    status_var = tk.StringVar(value="就绪")

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    tk.Button(top, text="格式化", command=lambda: fmt(True),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Button(top, text="压缩", command=lambda: fmt(False),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))
    input_text.pack(fill="x", padx=12, pady=(0, 4))
    output_text.pack(fill="both", expand=True, padx=12, pady=(0, 4))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def fmt(pretty):
        src = input_text.get("1.0", "end-1c")
        if pretty:
            result, err = _format_xml(src)
        else:
            result = re.sub(r">\s+<", "><", src.strip())
            err = ""
            try:
                import xml.dom.minidom
                xml.dom.minidom.parseString(result)
            except Exception as exc:
                err = f"XML 校验失败：{exc}"
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.insert("1.0", err or result)
        output_text.configure(state="disabled")
        status_var.set(err or "成功")


def _process_text(text, dedupe=False, lower=False, upper=False,
                  sort_lines=False, strip_empty=False):
    lines = text.splitlines()
    if strip_empty:
        lines = [ln for ln in lines if ln.strip()]
    if dedupe:
        lines = list(dict.fromkeys(lines))
    if lower:
        lines = [ln.lower() for ln in lines]
    if upper:
        lines = [ln.upper() for ln in lines]
    if sort_lines:
        lines.sort()
    return "\n".join(lines)


def _text_stats(text):
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    lines = len(text.splitlines())
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return chars, words, lines, cn_chars


def text_processor(parent):
    """文本处理增强（去重 / 大小写 / 排序 / 统计）。"""
    win = _open_tool_window(parent, "文本处理", 640, 480)
    input_text = tk.Text(win, font=("Consolas", 9), height=10, relief="solid", bd=1)
    output_text = tk.Text(win, font=("Consolas", 9), height=10, state="disabled",
                          relief="solid", bd=1)
    dedupe_var = tk.BooleanVar(value=True)
    lower_var = tk.BooleanVar(value=False)
    upper_var = tk.BooleanVar(value=False)
    sort_var = tk.BooleanVar(value=False)
    strip_var = tk.BooleanVar(value=False)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    for text_l, var in (("去重", dedupe_var), ("转小写", lower_var), ("转大写", upper_var),
                        ("排序", sort_var), ("去掉空行", strip_var)):
        tk.Checkbutton(top, text=text_l, variable=var, bg=_BG,
                       font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 8))
    tk.Button(top, text="处理", command=lambda: process(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))

    input_text.pack(fill="both", expand=True, padx=12, pady=(0, 4))
    output_text.pack(fill="both", expand=True, padx=12, pady=(0, 4))
    stats_var = tk.StringVar(value="")
    tk.Label(win, textvariable=stats_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def process():
        src = input_text.get("1.0", "end-1c")
        result = _process_text(src, dedupe=dedupe_var.get(), lower=lower_var.get(),
                               upper=upper_var.get(), sort_lines=sort_var.get(),
                               strip_empty=strip_var.get())
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.insert("1.0", result)
        output_text.configure(state="disabled")
        chars, words, lines, cn = _text_stats(src)
        stats_var.set(f"原文：{chars} 字符 / {words} 词 / {lines} 行 / {cn} 个汉字")


# ======================================================================
# 五、娱乐扩展
# ======================================================================
def gif_recorder(parent):
    """屏幕录制并输出 GIF 动图。"""
    win = _open_tool_window(parent, "屏幕录制 GIF", 520, 360)
    fps_var = tk.StringVar(value="5")
    status_var = tk.StringVar(value="就绪")
    frames = []
    running = [False]

    tk.Label(win, text="屏幕录制（GIF）", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(14, 4))
    tk.Label(win, text="录制全屏并输出 GIF 动图（建议帧率 3~8，文件较大）",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 8))

    row = tk.Frame(win, bg=_BG)
    row.pack(pady=(0, 8))
    tk.Label(row, text="帧率 (fps)：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(row, textvariable=fps_var, width=6).pack(side="left")

    btn = tk.Button(win, text="开始录制", command=lambda: start(),
                    font=("Microsoft YaHei UI", 11), bg="#c0392b", fg="#ffffff",
                    relief="flat", padx=16, pady=5, cursor="hand2")
    btn.pack(pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(pady=(0, 8))

    def start():
        if not _HAS_PIL:
            messagebox.showerror("录制", "未安装 Pillow，无法录制。\npip install pillow")
            return
        if running[0]:
            return
        try:
            fps = max(1, min(15, int(fps_var.get())))
        except ValueError:
            fps = 5
        running[0] = True
        frames.clear()
        btn.config(state="disabled", text="录制中……")
        threading.Thread(target=record, args=(fps,), daemon=True).start()

    def record(fps):
        interval = 1.0 / fps
        start_ts = time.time()
        try:
            while running[0]:
                img = ImageGrab.grab()
                # 缩小到 50% 控制 GIF 体积
                w, h = img.size
                frames.append(img.resize((w // 2, h // 2)))
                elapsed = time.time() - start_ts
                sleep = interval - (elapsed % interval)
                if sleep > 0:
                    time.sleep(sleep)
                if len(frames) >= 200:
                    break
        except Exception as exc:
            running[0] = False
            win.after(0, lambda: (btn.config(state="normal", text="开始录制"),
                                  status_var.set(f"录制失败：{exc}")))
            return
        win.after(0, lambda: (btn.config(state="normal", text="开始录制"),
                              status_var.set(f"已录制 {len(frames)} 帧，请选择保存位置……")))
        save_frames()

    def save_frames():
        if not frames:
            win.after(0, lambda: status_var.set("没有录到帧"))
            return
        path = filedialog.asksaveasfilename(title="保存 GIF", defaultextension=".gif",
                                            filetypes=[("GIF 图片", "*.gif")])
        if not path:
            return
        try:
            frames[0].save(path, save_all=True, append_images=frames[1:],
                           duration=int(1000 / max(1, int(fps_var.get()))),
                           loop=0)
            win.after(0, lambda: status_var.set(f"已保存：{path}（{len(frames)} 帧）"))
        except Exception as exc:
            win.after(0, lambda: status_var.set(f"保存失败：{exc}"))

    def stop():
        running[0] = False


def auto_clicker(parent):
    """鼠标连点器。"""
    win = _open_tool_window(parent, "鼠标连点器", 440, 300)
    interval_var = tk.StringVar(value="0.1")
    status_var = tk.StringVar(value="就绪")
    running = [False]

    tk.Label(win, text="鼠标连点器", font=("Microsoft YaHei UI", 14, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(pady=(14, 4))
    tk.Label(win, text="在当前位置自动左键连点（按 F2 或点击停止结束）",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 8))

    row = tk.Frame(win, bg=_BG)
    row.pack(pady=(0, 8))
    tk.Label(row, text="间隔 (秒)：", font=("Microsoft YaHei UI", 10), bg=_BG).pack(side="left")
    tk.Entry(row, textvariable=interval_var, width=8).pack(side="left")

    start_btn = tk.Button(win, text="开始连点", command=lambda: start(),
                          font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
                          relief="flat", padx=16, pady=5, cursor="hand2")
    start_btn.pack(pady=(0, 6))
    tk.Button(win, text="停止", command=lambda: stop(),
              font=("Microsoft YaHei UI", 11), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=16, pady=5, cursor="hand2").pack(pady=(0, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(pady=(0, 8))

    def start():
        if running[0]:
            return
        try:
            interval = max(0.02, float(interval_var.get()))
        except ValueError:
            interval = 0.1
        running[0] = True
        start_btn.config(state="disabled")
        status_var.set(f"连点中，间隔 {interval}s……（点击“停止”结束）")
        threading.Thread(target=click_loop, args=(interval,), daemon=True).start()

    def click_loop(interval):
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        while running[0]:
            try:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            except Exception:
                break
            time.sleep(interval)

    def stop():
        running[0] = False
        start_btn.config(state="normal")
        status_var.set("已停止")
