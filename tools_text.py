# -*- coding: utf-8 -*-
"""
tools_text.py —— 文本与办公工具集（6 个工具）

每个工具是一个函数，签名统一为 func(parent)（与 tools_system 相同）：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

工具列表：
    1. text_diff(parent)         文本差异对比（difflib 统一格式）
    2. json_tool(parent)         JSON 格式化 / 压缩 / 校验
    3. timestamp_convert(parent) 时间戳 ↔ 日期时间互转（自动识别秒/毫秒）
    4. color_picker(parent)      颜色拾取（取色器 / HEX 解析 / 复制）
    5. unit_convert(parent)      单位换算（数据大小、长度、重量、温度）
    6. password_gen(parent)      随机密码生成（可自定义字符集与长度）

本模块全部使用标准库，无第三方依赖。
"""
import difflib
import json
import re
import secrets
import string
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from tools_system import _open_tool_window

# 屏幕取色依赖 Pillow（可选，缺失时自动退回系统取色器）
try:
    from PIL import ImageGrab, ImageTk
    _HAS_PIL_PICKER = True
except ImportError:
    ImageGrab = ImageTk = None
    _HAS_PIL_PICKER = False

_BG = "#f5f6fa"
_TITLE_FG = "#1f2a3a"
_HINT_FG = "#7a8699"
_BTN_BG = "#3d5a80"
_BTN_FG = "#ffffff"


# ----------------------------------------------------------------------
# 1. 文本差异对比
# ----------------------------------------------------------------------
def _diff_texts(text_a, text_b):
    """对比两段文本，返回 (差异行列表, 统计文本)。"""
    a_lines = text_a.splitlines()
    b_lines = text_b.splitlines()
    diff = list(difflib.unified_diff(
        a_lines, b_lines, fromfile="文本A", tofile="文本B", lineterm=""))
    # 过滤掉文件头（---/+++），只保留真正的增删行
    changed = [ln for ln in diff
               if (ln.startswith("+") or ln.startswith("-"))
               and not ln.startswith(("+++", "---"))]
    if not changed:
        diff = []  # 两段文本完全一致
    stats = f"A：{len(a_lines)} 行，B：{len(b_lines)} 行，差异行：{len(changed)} 行"
    return diff, stats


def text_diff(parent):
    """文本差异对比工具。"""
    win = _open_tool_window(parent, "文本差异对比", 760, 520)

    top = tk.Frame(win, bg=_BG)
    top.pack(fill="x", padx=12, pady=(10, 4))
    tk.Label(top, text="文本差异对比", font=("Microsoft YaHei UI", 12, "bold"),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Button(top, text="对比", command=lambda: compare(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=14, cursor="hand2").pack(side="right")

    # 两个输入框并排
    editors = tk.Frame(win, bg=_BG)
    editors.pack(fill="both", expand=True, padx=12, pady=(0, 4))
    for side, label in (("left", "文本 A"), ("right", "文本 B")):
        col = tk.Frame(editors, bg=_BG)
        col.pack(side=side, fill="both", expand=True, padx=(0 if side == "left" else 6, 6 if side == "left" else 0))
        tk.Label(col, text=label, font=("Microsoft YaHei UI", 10),
                 bg=_BG, fg=_TITLE_FG).pack(anchor="w")
        text = tk.Text(col, font=("Consolas", 9), wrap="none",
                       bg="#ffffff", fg="#22303f", relief="solid", bd=1)
        sb = ttk.Scrollbar(col, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        if side == "left":
            text_a = text
        else:
            text_b = text

    # 结果区
    tk.Label(win, text="差异结果（- 为 A 独有，+ 为 B 独有）：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=12, pady=(2, 2))
    result = tk.Text(win, font=("Consolas", 9), wrap="none", state="disabled",
                     bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb2 = ttk.Scrollbar(win, command=result.yview)
    result.configure(yscrollcommand=sb2.set)
    sb2.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    result.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))

    stats_var = tk.StringVar(value="就绪")
    tk.Label(win, textvariable=stats_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def compare():
        diff, stats = _diff_texts(text_a.get("1.0", "end-1c"),
                                  text_b.get("1.0", "end-1c"))
        result.configure(state="normal")
        result.delete("1.0", "end")
        if diff:
            result.insert("1.0", "\n".join(diff))
        else:
            result.insert("1.0", "（两段文本完全一致）")
        result.configure(state="disabled")
        stats_var.set(stats)


# ----------------------------------------------------------------------
# 2. JSON 格式化
# ----------------------------------------------------------------------
def _format_json(text, indent=None):
    """格式化/压缩 JSON；返回 (结果文本, 错误信息)。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return "", f"JSON 解析失败：{exc}"
    if indent is None:
        result = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        result = json.dumps(data, ensure_ascii=False, indent=indent)
    return result, ""


def json_tool(parent):
    """JSON 格式化 / 压缩 / 校验工具。"""
    win = _open_tool_window(parent, "JSON 工具", 680, 520)

    tk.Label(win, text="输入 JSON：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=12, pady=(10, 2))
    input_text = tk.Text(win, font=("Consolas", 9), wrap="none",
                         bg="#ffffff", fg="#22303f", relief="solid", bd=1, height=8)
    input_text.pack(fill="x", padx=12, pady=(0, 4))

    btns = tk.Frame(win, bg=_BG)
    btns.pack(fill="x", padx=12, pady=(0, 4))
    tk.Button(btns, text="格式化", command=lambda: format_json(2),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=14, cursor="hand2").pack(side="left")
    tk.Button(btns, text="压缩", command=lambda: format_json(None),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Button(btns, text="清空", command=lambda: (input_text.delete("1.0", "end"),
                                                  output_text.configure(state="normal"),
                                                  output_text.delete("1.0", "end"),
                                                  output_text.configure(state="disabled"),
                                                  status_var.set("就绪")),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", fg=_TITLE_FG,
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))

    tk.Label(win, text="输出：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(anchor="w", padx=12, pady=(2, 2))
    output_text = tk.Text(win, font=("Consolas", 9), wrap="none", state="disabled",
                          bg="#ffffff", fg="#22303f", relief="solid", bd=1)
    sb = ttk.Scrollbar(win, command=output_text.yview)
    output_text.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y", padx=(0, 12), pady=(0, 6))
    output_text.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 6))

    status_var = tk.StringVar(value="就绪")
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 9),
             bg=_BG, fg=_HINT_FG, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def format_json(indent):
        result, err = _format_json(input_text.get("1.0", "end-1c"), indent)
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        if err:
            output_text.insert("1.0", err)
            status_var.set("格式化失败")
        else:
            output_text.insert("1.0", result)
            status_var.set(f"成功：{len(result)} 字符")
        output_text.configure(state="disabled")


# ----------------------------------------------------------------------
# 3. 时间戳转换
# ----------------------------------------------------------------------
def _parse_timestamp(text):
    """解析时间戳（自动识别秒/毫秒），返回 (秒时间戳 float, 是否毫秒)。"""
    text = text.strip()
    if not text.isdigit():
        raise ValueError("时间戳必须为数字")
    if len(text) >= 13:
        return int(text) / 1000.0, True
    return float(text), False


def _ts_to_str(ts, utc=False):
    """时间戳（秒）→ 格式化时间字符串。"""
    if utc:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _str_to_ts(text):
    """日期时间字符串 → 时间戳（秒）。"""
    candidates = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                  "%Y/%m/%d %H:%M:%S", "%Y年%m月%d日 %H:%M:%S"]
    for fmt in candidates:
        try:
            return time.mktime(time.strptime(text.strip(), fmt))
        except ValueError:
            continue
    raise ValueError("无法识别的日期格式，请使用 YYYY-MM-DD HH:MM:SS")


def timestamp_convert(parent):
    """时间戳 ↔ 日期时间互转工具。"""
    win = _open_tool_window(parent, "时间戳转换", 560, 340)
    win.resizable(False, False)

    ts_var = tk.StringVar()
    ts_result_var = tk.StringVar(value="--")
    date_var = tk.StringVar()
    date_result_var = tk.StringVar(value="--")

    # 时间戳 → 日期
    row1 = tk.Frame(win, bg=_BG)
    row1.pack(fill="x", padx=14, pady=(14, 4))
    tk.Label(row1, text="时间戳：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row1, textvariable=ts_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True, padx=(0, 6))
    tk.Button(row1, text="转换", command=lambda: ts_to_date(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Label(win, textvariable=ts_result_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="w", relief="solid", bd=1,
             padx=6).pack(fill="x", padx=14, pady=(0, 4))
    tk.Label(win, text="（自动识别秒/毫秒时间戳，结果同时给出本地时间与 UTC 时间）",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG,
             anchor="w").pack(fill="x", padx=14, pady=(0, 8))

    # 日期 → 时间戳
    row2 = tk.Frame(win, bg=_BG)
    row2.pack(fill="x", padx=14, pady=(0, 4))
    tk.Label(row2, text="日期时间：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row2, textvariable=date_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True, padx=(0, 6))
    tk.Button(row2, text="转换", command=lambda: date_to_ts(),
              font=("Microsoft YaHei UI", 10), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left")
    tk.Label(win, textvariable=date_result_var, font=("Consolas", 10), bg="#ffffff",
             fg="#22303f", anchor="w", relief="solid", bd=1,
             padx=6).pack(fill="x", padx=14, pady=(0, 10))

    # “当前时间”快捷填充
    tk.Button(win, text="填入当前时间戳", command=lambda: ts_var.set(str(int(time.time()))),
              font=("Microsoft YaHei UI", 9), bg="#aab4c4", fg=_TITLE_FG,
              relief="flat", padx=10, cursor="hand2").pack(anchor="w", padx=14, pady=(0, 10))

    def ts_to_date():
        try:
            ts, is_ms = _parse_timestamp(ts_var.get())
        except ValueError as exc:
            ts_result_var.set(f"错误：{exc}")
            return
        ts_result_var.set(
            f"本地：{_ts_to_str(ts)}     UTC：{_ts_to_str(ts, utc=True)}"
            f"{'（毫秒时间戳）' if is_ms else ''}")

    def date_to_ts():
        try:
            ts = _str_to_ts(date_var.get())
        except ValueError as exc:
            date_result_var.set(f"错误：{exc}")
            return
        date_result_var.set(f"秒：{int(ts)}    毫秒：{int(ts * 1000)}")


# ----------------------------------------------------------------------
# 4. 颜色拾取
# ----------------------------------------------------------------------
def _grab_pixel(x, y):
    """读取屏幕坐标 (x, y) 处的颜色，返回 (hex, (r,g,b))；失败返回 None。"""
    if not _HAS_PIL_PICKER:
        return None
    try:
        img = ImageGrab.grab((x, y, x + 1, y + 1))
        rgb = img.getpixel((0, 0))[:3]
        return "#%02X%02X%02X" % rgb, rgb
    except Exception:
        return None


def _start_screen_picker(win, on_pick):
    """全屏屏幕取色：移动鼠标实时预览颜色，左键确认，Esc 或右键取消。"""
    if not _HAS_PIL_PICKER:
        messagebox.showwarning("颜色拾取", "屏幕取色需要 Pillow。\n请先执行：pip install pillow")
        return
    win.withdraw()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    overlay = tk.Toplevel(win)
    overlay.overrideredirect(True)
    overlay.geometry(f"{screen_w}x{screen_h}+0+0")
    overlay.attributes("-topmost", True)
    canvas = tk.Canvas(overlay, bg="#000000", cursor="crosshair", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    info = tk.Label(overlay, font=("Microsoft YaHei UI", 12),
                    bg="#1f2a3a", fg="#ffffff", justify="left")
    info.place(x=12, y=12)
    preview = tk.Label(overlay, bg="#ffffff", bd=2, relief="solid")
    preview.place(x=12, y=58)
    state = {"hex": None, "rgb": None}

    def update_pixel(x, y):
        result = _grab_pixel(x, y)
        if not result:
            return
        hexv, rgb = result
        state["hex"], state["rgb"] = hexv, rgb
        # 放大光标周围 24x24 区域，便于精确取色
        try:
            patch = ImageGrab.grab((x - 12, y - 12, x + 12, y + 12)).resize((96, 96))
            photo = ImageTk.PhotoImage(patch)
            preview.config(image=photo, bg=hexv)
            preview.image = photo  # 防止被垃圾回收
        except Exception:
            preview.config(bg=hexv)
        info.config(text=f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}    HEX: {hexv}\n"
                         f"左键确定，Esc / 右键取消")

    def on_motion(event):
        update_pixel(event.x, event.y)

    def on_confirm(event):
        update_pixel(event.x, event.y)
        close()
        if state["hex"]:
            on_pick(state["hex"], state["rgb"])

    def on_cancel(_event=None):
        close()

    def close():
        overlay.destroy()
        win.deiconify()

    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Button-1>", on_confirm)
    canvas.bind("<Button-3>", on_cancel)
    overlay.bind("<Escape>", on_cancel)


def color_picker(parent):
    """颜色拾取工具（屏幕取色 / 系统取色器 / HEX 解析 / 复制到剪贴板）。"""
    win = _open_tool_window(parent, "颜色拾取", 440, 420)
    win.resizable(False, False)

    swatch = tk.Label(win, bg="#ffffff", width=24, height=7, relief="solid", bd=1)
    swatch.pack(padx=14, pady=(14, 8))
    rgb_var = tk.StringVar(value="RGB: --")
    hex_var = tk.StringVar(value="HEX: --")
    hex_input_var = tk.StringVar(value="#3498db")

    tk.Label(win, textvariable=rgb_var, font=("Consolas", 11), bg=_BG, fg=_TITLE_FG).pack()
    tk.Label(win, textvariable=hex_var, font=("Consolas", 11), bg=_BG, fg=_TITLE_FG).pack(pady=(0, 8))

    btn_row = tk.Frame(win, bg=_BG)
    btn_row.pack(pady=(0, 8))
    tk.Button(btn_row, text="屏幕取色", command=lambda: _start_screen_picker(win, on_picked),
              font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=16, pady=4, cursor="hand2").pack(side="left")
    tk.Button(btn_row, text="系统取色器", command=lambda: pick(),
              font=("Microsoft YaHei UI", 11), bg="#aab4c4", fg=_TITLE_FG,
              relief="flat", padx=16, pady=4, cursor="hand2").pack(side="left", padx=(10, 0))

    row = tk.Frame(win, bg=_BG)
    row.pack(fill="x", padx=14, pady=(0, 4))
    tk.Label(row, text="HEX：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Entry(row, textvariable=hex_input_var, font=("Consolas", 10), width=12).pack(side="left")
    tk.Button(row, text="解析", command=lambda: parse_hex(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))
    tk.Button(row, text="复制 HEX", command=lambda: copy_hex(),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", fg=_TITLE_FG,
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(8, 0))

    tk.Label(win, text="提示：屏幕取色移动鼠标即可实时预览，左键确定；系统取色器为 Windows 原生对话框",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(8, 10))

    def apply(hexv, rgb):
        swatch.config(bg=hexv)
        rgb_var.set(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        hex_var.set(f"HEX: {hexv.upper()}")

    def pick():
        rgb, hexv = colorchooser.askcolor(title="选择颜色", parent=win)
        if rgb and hexv:
            apply(hexv, [int(c) for c in rgb])

    def on_picked(hexv, rgb):
        """屏幕取色回调（主线程中执行）。"""
        apply(hexv, [int(c) for c in rgb])

    def parse_hex():
        text = hex_input_var.get().strip()
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
            messagebox.showwarning("颜色拾取", "HEX 格式应为 #RRGGBB（6 位十六进制）。")
            return
        h = text.lstrip("#")
        rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        apply("#" + h.upper(), rgb)

    def copy_hex():
        text = hex_var.get().replace("HEX: ", "")
        if text == "--":
            messagebox.showinfo("颜色拾取", "请先取色或解析 HEX。")
            return
        win.clipboard_clear()
        win.clipboard_append(text)
        win.update()
        messagebox.showinfo("颜色拾取", f"已复制 {text} 到剪贴板。")


# ----------------------------------------------------------------------
# 5. 单位换算
# ----------------------------------------------------------------------
# 类别 -> 单位 -> 相对基准的倍数（温度单独处理）
_UNIT_TABLES = {
    "数据大小": {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3,
                 "TB": 1024 ** 4, "PB": 1024 ** 5},
    "长度": {"毫米": 0.001, "厘米": 0.01, "米": 1, "千米": 1000,
             "英寸": 0.0254, "英尺": 0.3048, "码": 0.9144, "英里": 1609.344},
    "重量": {"毫克": 0.001, "克": 1, "千克": 1000, "吨": 1e6,
             "斤": 500, "两": 50, "磅": 453.59237, "盎司": 28.349523125},
    "温度": {"摄氏度": "C", "华氏度": "F", "开尔文": "K"},
}


def _convert_unit(category, value, from_unit, to_unit):
    """单位换算；返回换算结果数值（温度按非线性公式）。"""
    if category == "温度":
        # 中文单位名 -> 代码（C/F/K），统一转到摄氏度再转出
        code_from = _UNIT_TABLES["温度"][from_unit]
        code_to = _UNIT_TABLES["温度"][to_unit]
        celsius = {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[code_from]
        if code_to == "C":
            return celsius
        if code_to == "F":
            return celsius * 9 / 5 + 32
        return celsius + 273.15
    return value * _UNIT_TABLES[category][from_unit] / _UNIT_TABLES[category][to_unit]


def unit_convert(parent):
    """单位换算工具。"""
    win = _open_tool_window(parent, "单位换算", 520, 320)
    win.resizable(False, False)

    category_var = tk.StringVar(value="数据大小")
    value_var = tk.StringVar(value="1")
    from_var = tk.StringVar(value="MB")
    to_var = tk.StringVar(value="KB")
    result_var = tk.StringVar(value="--")

    def refresh_units(*_):
        units = list(_UNIT_TABLES[category_var.get()].keys())
        combo_from["values"] = units
        combo_to["values"] = units
        if from_var.get() not in units:
            from_var.set(units[0])
        if to_var.get() not in units:
            to_var.set(units[1] if len(units) > 1 else units[0])

    form = tk.Frame(win, bg=_BG)
    form.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(form, text="类别：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=0, column=0, sticky="w", pady=4)
    category_combo = ttk.Combobox(form, textvariable=category_var,
                                  values=list(_UNIT_TABLES.keys()),
                                  state="readonly", width=10)
    category_combo.grid(row=0, column=1, sticky="w", pady=4)
    category_combo.bind("<<ComboboxSelected>>", refresh_units)

    tk.Label(form, text="数值：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=1, column=0, sticky="w", pady=4)
    tk.Entry(form, textvariable=value_var, font=("Consolas", 10), width=12).grid(row=1, column=1, sticky="w", pady=4)

    tk.Label(form, text="从：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=2, column=0, sticky="w", pady=4)
    combo_from = ttk.Combobox(form, textvariable=from_var, state="readonly", width=10)
    combo_from.grid(row=2, column=1, sticky="w", pady=4)
    tk.Label(form, text="到：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).grid(row=3, column=0, sticky="w", pady=4)
    combo_to = ttk.Combobox(form, textvariable=to_var, state="readonly", width=10)
    combo_to.grid(row=3, column=1, sticky="w", pady=4)

    tk.Button(win, text="换算", command=lambda: convert(),
              font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=16, pady=4, cursor="hand2").pack(pady=(4, 6))
    tk.Label(win, textvariable=result_var, font=("Consolas", 13, "bold"),
             bg="#ffffff", fg="#27ae60", relief="solid", bd=1,
             padx=8).pack(fill="x", padx=14, pady=(0, 10))

    refresh_units()

    def convert():
        try:
            value = float(value_var.get())
        except ValueError:
            messagebox.showwarning("单位换算", "数值必须为数字。")
            return
        category = category_var.get()
        try:
            result = _convert_unit(category, value, from_var.get(), to_var.get())
        except KeyError:
            result_var.set("单位无效")
            return
        result_var.set(f"{value:g} {from_var.get()} = {result:g} {to_var.get()}")


# ----------------------------------------------------------------------
# 6. 随机密码生成
# ----------------------------------------------------------------------
# 易混淆字符（0/O、1/l/I、| 等）
_AMBIGUOUS = "0O1lI|`'\""


def _generate_password(length=16, use_upper=True, use_lower=True, use_digits=True,
                       use_symbols=True, exclude_ambiguous=False):
    """生成随机密码；返回字符串。"""
    chars = ""
    if use_upper:
        chars += string.ascii_uppercase
    if use_lower:
        chars += string.ascii_lowercase
    if use_digits:
        chars += string.digits
    if use_symbols:
        chars += string.punctuation
    if not chars:
        raise ValueError("至少选择一种字符类型")
    if exclude_ambiguous:
        chars = "".join(c for c in chars if c not in _AMBIGUOUS)
        if not chars:
            raise ValueError("排除混淆字符后无可用字符")
    length = max(4, min(int(length), 128))
    return "".join(secrets.choice(chars) for _ in range(length))


def password_gen(parent):
    """随机密码生成工具。"""
    win = _open_tool_window(parent, "随机密码生成", 480, 400)
    win.resizable(False, False)

    length_var = tk.StringVar(value="16")
    upper_var = tk.BooleanVar(value=True)
    lower_var = tk.BooleanVar(value=True)
    digits_var = tk.BooleanVar(value=True)
    symbols_var = tk.BooleanVar(value=True)
    exclude_var = tk.BooleanVar(value=False)
    result_var = tk.StringVar(value="（点击“生成”得到随机密码）")

    row = tk.Frame(win, bg=_BG)
    row.pack(fill="x", padx=14, pady=(14, 6))
    tk.Label(row, text="长度：", font=("Microsoft YaHei UI", 10),
             bg=_BG, fg=_TITLE_FG).pack(side="left")
    tk.Spinbox(row, from_=4, to=64, textvariable=length_var, width=6,
               font=("Consolas", 10)).pack(side="left")

    opts = tk.Frame(win, bg=_BG)
    opts.pack(fill="x", padx=14, pady=(0, 6))
    for text, var in (("大写字母", upper_var), ("小写字母", lower_var),
                      ("数字", digits_var), ("符号", symbols_var)):
        tk.Checkbutton(opts, text=text, variable=var, bg=_BG,
                       font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 10))
    tk.Checkbutton(opts, text="排除易混淆字符(0O1lI|)", variable=exclude_var,
                   bg=_BG, font=("Microsoft YaHei UI", 10)).pack(side="left")

    tk.Button(win, text="生成密码", command=lambda: generate(),
              font=("Microsoft YaHei UI", 11), bg=_BTN_BG, fg=_BTN_FG,
              relief="flat", padx=16, pady=4, cursor="hand2").pack(pady=(4, 6))

    tk.Entry(win, textvariable=result_var, font=("Consolas", 11),
             state="readonly", relief="solid", bd=1,
             justify="center").pack(fill="x", padx=14, pady=(0, 6))
    tk.Button(win, text="复制到剪贴板", command=lambda: copy_pwd(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(pady=(0, 8))
    tk.Label(win, text="使用 secrets 模块的密码学安全随机源生成",
             font=("Microsoft YaHei UI", 9), bg=_BG, fg=_HINT_FG).pack(pady=(0, 10))

    def generate():
        try:
            pwd = _generate_password(
                length=int(length_var.get() or 16),
                use_upper=upper_var.get(), use_lower=lower_var.get(),
                use_digits=digits_var.get(), use_symbols=symbols_var.get(),
                exclude_ambiguous=exclude_var.get())
        except ValueError as exc:
            messagebox.showwarning("密码生成", str(exc))
            return
        result_var.set(pwd)

    def copy_pwd():
        pwd = result_var.get()
        if pwd.startswith("（"):
            messagebox.showinfo("密码生成", "请先生成密码。")
            return
        win.clipboard_clear()
        win.clipboard_append(pwd)
        win.update()
        messagebox.showinfo("密码生成", "已复制到剪贴板。")
