# -*- coding: utf-8 -*-
"""
tools_media.py —— 图像与媒体工具集（5 个工具）

每个工具是一个函数，签名统一为 func(parent)（与 tools_system 相同）：
    parent 为父窗口（Tk / Toplevel），函数内部创建一个 Toplevel 工具窗口。

工具列表：
    1. image_convert(parent)   图片格式转换（PNG/JPEG/BMP/GIF/WEBP/TIFF）
    2. image_compress(parent)  图片压缩（质量 / 格式选择，显示压缩前后大小）
    3. screenshot(parent)      截图（全屏 / 鼠标拖选区域）
    4. draw_board(parent)      简易绘图板（画线、橡皮、改色，保存为 PNG）
    5. qr_generator(parent)    二维码生成（qrcode，需 pip install qrcode[pil]）

依赖说明：
    - Pillow 可选：图片转换/压缩/截图/绘图板保存均依赖它，缺失时给出安装提示；
    - qrcode 可选：缺失时给出安装提示。
"""
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from tools_system import _open_tool_window, _run_in_thread

# ---------- 可选依赖 ----------
try:
    from PIL import Image, ImageDraw, ImageGrab, ImageTk
    _HAS_PIL = True
except ImportError:
    Image = ImageDraw = ImageGrab = ImageTk = None
    _HAS_PIL = False

try:
    import qrcode
    _HAS_QRCODE = True
except ImportError:
    qrcode = None
    _HAS_QRCODE = False

# 图片格式转换支持的目标格式
CONVERT_FORMATS = ["PNG", "JPEG", "BMP", "GIF", "WEBP", "TIFF"]


def _require_pil(win):
    """Pillow 未安装时弹窗提示并返回 False。"""
    if not _HAS_PIL:
        messagebox.showerror(
            "图像工具",
            "未安装 Pillow，无法使用该功能。\n请先执行：pip install pillow")
    return _HAS_PIL


def _ask_image_file(title="选择图片文件"):
    """弹出图片文件选择对话框。"""
    return filedialog.askopenfilename(
        title=title,
        filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff"),
                   ("所有文件", "*.*")])


# ----------------------------------------------------------------------
# 1. 图片格式转换
# ----------------------------------------------------------------------
def _convert_image(src, dst, fmt):
    """把图片转换为指定格式并保存，返回目标路径。"""
    with Image.open(src) as img:
        # JPEG/BMP 不支持透明通道，先转为 RGB
        if fmt in ("JPEG", "BMP"):
            img = img.convert("RGB")
        img.save(dst, format=fmt)
    return dst


def image_convert(parent):
    """图片格式转换工具。"""
    win = _open_tool_window(parent, "图片格式转换", 520, 300)
    win.resizable(False, False)

    file_var = tk.StringVar()
    fmt_var = tk.StringVar(value="PNG")
    status_var = tk.StringVar(value="就绪")

    row0 = tk.Frame(win, bg="#f5f6fa")
    row0.pack(fill="x", padx=14, pady=(14, 4))
    tk.Label(row0, text="图片：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(row0, textvariable=file_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row0, text="浏览…", command=lambda: file_var.set(_ask_image_file()),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
              padx=10, cursor="hand2").pack(side="left", padx=(6, 0))

    row1 = tk.Frame(win, bg="#f5f6fa")
    row1.pack(fill="x", padx=14, pady=(6, 4))
    tk.Label(row1, text="目标格式：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    ttk.Combobox(row1, textvariable=fmt_var, values=CONVERT_FORMATS,
                 state="readonly", width=10).pack(side="left")

    tk.Button(win, text="转换并保存", command=lambda: convert(),
              font=("Microsoft YaHei UI", 11), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=16, pady=4, cursor="hand2").pack(pady=(8, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(pady=(0, 8))

    def convert():
        if not _require_pil(win):
            return
        src = file_var.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showwarning("图片格式转换", "请先选择有效的图片文件。")
            return
        fmt = fmt_var.get().upper()
        ext = ".jpg" if fmt == "JPEG" else "." + fmt.lower()
        dst = filedialog.asksaveasfilename(
            title="保存转换后的图片", defaultextension=ext,
            filetypes=[(fmt, f"*.{ext.lstrip('.')}")])
        if not dst:
            return
        status_var.set("正在转换……")
        _run_in_thread(win, lambda: _convert_image(src, dst, fmt), on_done)

    def on_done(kind, payload):
        if kind == "error":
            status_var.set(f"转换失败：{payload}")
            return
        status_var.set(f"转换完成：{payload}")
        messagebox.showinfo("图片格式转换", f"已保存到：\n{payload}")


# ----------------------------------------------------------------------
# 2. 图片压缩
# ----------------------------------------------------------------------
def _compress_image(src, dst, fmt, quality):
    """压缩图片，返回 (原始大小, 压缩后大小)。"""
    orig = os.path.getsize(src)
    with Image.open(src) as img:
        if fmt == "PNG":
            img.save(dst, format="PNG", optimize=True)
        else:
            img = img.convert("RGB")
            img.save(dst, format=fmt, quality=quality, optimize=True)
    return orig, os.path.getsize(dst)


def image_compress(parent):
    """图片压缩工具。"""
    win = _open_tool_window(parent, "图片压缩", 520, 380)
    win.resizable(False, False)

    file_var = tk.StringVar()
    quality_var = tk.IntVar(value=70)
    fmt_var = tk.StringVar(value="JPEG")
    status_var = tk.StringVar(value="就绪")

    row0 = tk.Frame(win, bg="#f5f6fa")
    row0.pack(fill="x", padx=14, pady=(14, 4))
    tk.Label(row0, text="图片：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(row0, textvariable=file_var, font=("Consolas", 10)).pack(side="left", fill="x", expand=True)
    tk.Button(row0, text="浏览…", command=lambda: file_var.set(_ask_image_file()),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
              padx=10, cursor="hand2").pack(side="left", padx=(6, 0))

    row1 = tk.Frame(win, bg="#f5f6fa")
    row1.pack(fill="x", padx=14, pady=(6, 4))
    tk.Label(row1, text="质量：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Scale(row1, from_=1, to=100, orient="horizontal", variable=quality_var,
             bg="#f5f6fa", highlightthickness=0).pack(side="left", fill="x", expand=True)
    tk.Label(row1, text="输出格式：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left", padx=(8, 0))
    ttk.Combobox(row1, textvariable=fmt_var, values=["JPEG", "WEBP", "PNG"],
                 state="readonly", width=8).pack(side="left")

    tk.Button(win, text="压缩并保存", command=lambda: compress(),
              font=("Microsoft YaHei UI", 11), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=16, pady=4, cursor="hand2").pack(pady=(8, 6))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a", wraplength=480,
             justify="left").pack(padx=14, pady=(0, 8))

    def compress():
        if not _require_pil(win):
            return
        src = file_var.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showwarning("图片压缩", "请先选择有效的图片文件。")
            return
        fmt = fmt_var.get().upper()
        ext = ".jpg" if fmt == "JPEG" else "." + fmt.lower()
        dst = filedialog.asksaveasfilename(
            title="保存压缩后的图片", defaultextension=ext,
            filetypes=[(fmt, f"*.{ext.lstrip('.')}")])
        if not dst:
            return
        status_var.set("正在压缩……")
        _run_in_thread(win, lambda: _compress_image(src, dst, fmt, quality_var.get()), on_done)

    def on_done(kind, payload):
        if kind == "error":
            status_var.set(f"压缩失败：{payload}")
            return
        orig, comp = payload
        saved = (1 - comp / orig) * 100 if orig else 0
        status_var.set(
            f"压缩完成：{orig / 1024:.1f} KB → {comp / 1024:.1f} KB"
            f"（节省 {saved:.1f}%）")


# ----------------------------------------------------------------------
# 3. 截图（全屏 / 区域）
# ----------------------------------------------------------------------
def screenshot(parent):
    """截图工具（全屏或拖选区域）。"""
    win = _open_tool_window(parent, "截图工具", 420, 260)
    win.resizable(False, False)

    status_var = tk.StringVar(value="就绪")

    tk.Label(win, text="截图工具", font=("Microsoft YaHei UI", 14, "bold"),
             bg="#f5f6fa", fg="#1f2a3a").pack(pady=(16, 10))

    tk.Button(win, text="全屏截图", command=lambda: full(),
              font=("Microsoft YaHei UI", 12), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=20, pady=6, cursor="hand2").pack(fill="x", padx=60, pady=4)
    tk.Button(win, text="区域截图（拖选矩形）", command=lambda: region(),
              font=("Microsoft YaHei UI", 12), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=20, pady=6, cursor="hand2").pack(fill="x", padx=60, pady=4)
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(pady=(10, 8))

    def grab_and_save(bbox=None):
        if not _require_pil(win):
            return
        dst = filedialog.asksaveasfilename(
            title="保存截图", defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")])
        if not dst:
            return
        try:
            img = ImageGrab.grab(bbox=bbox)
            img.save(dst)
        except Exception as exc:
            status_var.set(f"截图失败：{exc}")
            return
        status_var.set(f"已保存：{dst}")

    def full():
        grab_and_save(None)

    def region():
        if not _require_pil(win):
            return
        win.withdraw()  # 隐藏主工具窗口
        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        overlay = tk.Toplevel(win)
        overlay.overrideredirect(True)                 # 无边框全屏
        overlay.geometry(f"{screen_w}x{screen_h}+0+0")
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.25)             # 半透明遮罩
        canvas = tk.Canvas(overlay, bg="#000000", cursor="crosshair",
                           highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        start = {}
        rect_id = [None]

        def on_press(event):
            start["x"], start["y"] = event.x, event.y
            rect_id[0] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="#ff4d4f", width=2)

        def on_drag(event):
            if rect_id[0] is not None:
                canvas.coords(rect_id[0], start["x"], start["y"], event.x, event.y)

        def on_release(event):
            x1, y1 = start["x"], start["y"]
            x2, y2 = event.x, event.y
            overlay.destroy()
            win.deiconify()
            bbox = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            if bbox[2] - bbox[0] >= 2 and bbox[3] - bbox[1] >= 2:
                grab_and_save(bbox)
            else:
                status_var.set("区域太小，已取消")

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)


# ----------------------------------------------------------------------
# 4. 简易绘图板
# ----------------------------------------------------------------------
def draw_board(parent):
    """简易绘图板（画笔 / 橡皮 / 颜色 / 粗细，保存为 PNG）。"""
    win = _open_tool_window(parent, "绘图板", 720, 540)

    canvas = tk.Canvas(win, bg="#ffffff", width=680, height=420,
                       cursor="crosshair", relief="solid", bd=1)
    canvas.pack(padx=14, pady=(14, 6))

    strokes = []          # [{color, width, points: [(x, y), ...]}]
    current = [None]      # 当前笔画（闭包内可改）
    color_var = tk.StringVar(value="#1f2a3a")
    width_var = tk.IntVar(value=3)
    eraser_var = tk.BooleanVar(value=False)

    def on_press(event):
        color = "#ffffff" if eraser_var.get() else color_var.get()
        width = 16 if eraser_var.get() else width_var.get()
        stroke = {"color": color, "width": width, "points": [(event.x, event.y)]}
        strokes.append(stroke)
        current[0] = stroke

    def on_drag(event):
        stroke = current[0]
        if stroke is None:
            return
        stroke["points"].append((event.x, event.y))
        canvas.delete("current_stroke")
        pts = stroke["points"]
        if len(pts) >= 2:
            canvas.create_line(pts, fill=stroke["color"], width=stroke["width"],
                               smooth=True, capstyle="round", tags="current_stroke")

    def on_release(event):
        current[0] = None
        # 关键修复：完成一笔后移除“当前笔画”标签，
        # 否则下一笔的 canvas.delete("current_stroke") 会把上一笔也删掉
        canvas.dtag("current_stroke", "current_stroke")

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)

    # 控制区
    controls = tk.Frame(win, bg="#f5f6fa")
    controls.pack(fill="x", padx=14, pady=(0, 6))
    tk.Button(controls, text="颜色", command=lambda: pick_color(),
              font=("Microsoft YaHei UI", 10), bg="#aab4c4", relief="flat",
              padx=12, cursor="hand2").pack(side="left")
    tk.Scale(controls, from_=1, to=12, orient="horizontal", variable=width_var,
             label="粗细", bg="#f5f6fa", highlightthickness=0).pack(side="left", padx=(10, 0))
    tk.Checkbutton(controls, text="橡皮", variable=eraser_var, bg="#f5f6fa",
                   font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(10, 0))
    tk.Button(controls, text="清空", command=lambda: clear_board(),
              font=("Microsoft YaHei UI", 10), bg="#c0392b", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Button(controls, text="保存 PNG", command=lambda: save_png(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=12, cursor="hand2").pack(side="right")

    status = tk.Label(win, text="", font=("Microsoft YaHei UI", 9),
                      bg="#f5f6fa", fg="#7a8699", anchor="w")
    status.pack(fill="x", padx=14, pady=(0, 8))

    def pick_color():
        rgb, hexv = colorchooser.askcolor(color=color_var.get(), title="选择画笔颜色", parent=win)
        if hexv:
            color_var.set(hexv)

    def clear_board():
        canvas.delete("all")
        strokes.clear()
        status.config(text="已清空")

    def save_png():
        if not _require_pil(win):
            return
        dst = filedialog.asksaveasfilename(
            title="保存绘图", defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")])
        if not dst:
            return
        img = Image.new("RGB", (680, 420), "#ffffff")
        draw = ImageDraw.Draw(img)
        for stroke in strokes:
            pts = stroke["points"]
            if len(pts) >= 2:
                draw.line(pts, fill=stroke["color"], width=stroke["width"], joint="curve")
            elif pts:
                x, y = pts[0]
                r = stroke["width"] / 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=stroke["color"])
        img.save(dst)
        status.config(text=f"已保存：{dst}")


# ----------------------------------------------------------------------
# 5. 二维码生成
# ----------------------------------------------------------------------
def qr_generator(parent):
    """二维码生成工具（qrcode）。"""
    win = _open_tool_window(parent, "二维码生成", 520, 460)
    win.resizable(False, False)

    box_var = tk.StringVar(value="6")
    border_var = tk.StringVar(value="2")
    status_var = tk.StringVar(value="就绪")
    text_box = tk.Text(win, font=("Consolas", 10), height=4, width=40,
                       relief="solid", bd=1)
    preview = tk.Label(win, bg="#f5f6fa")
    preview.pack(pady=(0, 4))

    tk.Label(win, text="二维码内容：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(anchor="w", padx=14, pady=(12, 2))
    text_box.pack(fill="x", padx=14, pady=(0, 6))

    row = tk.Frame(win, bg="#f5f6fa")
    row.pack(fill="x", padx=14, pady=(0, 6))
    tk.Label(row, text="块大小：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(row, textvariable=box_var, width=5).pack(side="left")
    tk.Label(row, text="   边框：", font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(side="left")
    tk.Entry(row, textvariable=border_var, width=5).pack(side="left")

    btns = tk.Frame(win, bg="#f5f6fa")
    btns.pack(fill="x", padx=14, pady=(0, 6))
    tk.Button(btns, text="生成预览", command=lambda: build(),
              font=("Microsoft YaHei UI", 10), bg="#3d5a80", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left")
    tk.Button(btns, text="保存图片", command=lambda: save_qr(),
              font=("Microsoft YaHei UI", 10), bg="#27ae60", fg="#ffffff",
              relief="flat", padx=14, cursor="hand2").pack(side="left", padx=(10, 0))
    tk.Label(win, textvariable=status_var, font=("Microsoft YaHei UI", 10),
             bg="#f5f6fa", fg="#1f2a3a").pack(pady=(0, 10))

    def build():
        if not _HAS_QRCODE:
            messagebox.showerror(
                "二维码", "未安装 qrcode，无法生成。\n请先执行：pip install qrcode[pil]")
            return
        if not _HAS_PIL:
            messagebox.showerror("二维码", "未安装 Pillow（qrcode 依赖）。\n请先执行：pip install pillow")
            return
        text = text_box.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("二维码", "请输入要编码的内容。")
            return
        try:
            box = max(1, int(box_var.get()))
            border = max(0, int(border_var.get()))
        except ValueError:
            messagebox.showwarning("二维码", "块大小/边框必须为整数。")
            return
        qr = qrcode.QRCode(box_size=box, border=border)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        win._qr_img = img  # 保存引用供“保存图片”使用
        # 预览
        photo = ImageTk.PhotoImage(img.resize((240, 240)))
        win._qr_photo = photo
        preview.config(image=photo)
        status_var.set("已生成，可点击“保存图片”")

    def save_qr():
        if not hasattr(win, "_qr_img"):
            messagebox.showwarning("二维码", "请先生成预览。")
            return
        dst = filedialog.asksaveasfilename(
            title="保存二维码", defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")])
        if not dst:
            return
        win._qr_img.save(dst)
        status_var.set(f"已保存：{dst}")
