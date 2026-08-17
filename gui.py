# -*- coding: utf-8 -*-
"""
gui.py —— 主界面模块

定义 PCMApp 类，负责创建 PCM 电脑优化器的主窗口：
    - 左侧：180 宽菜单栏，含“磁盘清理 / 多线程下载 / 实用工具”三个按钮；
    - 右侧：内容区，根据所选页面显示对应内容。
      · 磁盘清理页：后台线程扫描垃圾文件，实时刷新，完成后询问是否移入回收站；
      · 多线程下载页：创建 Downloader 下载器，支持断点续传、暂停/继续、
        限速，进度条与日志实时更新；
      · 实用工具页：四个工具分组（可滚动）——系统工具 10 个、网络工具 5 个、
        图像媒体 5 个（格式转换/压缩/截图/绘图板/二维码）、文本办公 6 个
        （差异对比/JSON/时间戳/取色/单位换算/密码生成）。
    所有工作线程的回调都通过队列 + after() 轮询转发到主线程，保证线程安全。
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import disk_cleaner
import downloader
import tools_advanced
import tools_media
import tools_network
import tools_security
import tools_system
import tools_text
import utils

# ---------- 界面配色（深色菜单 + 浅色内容区） ----------
MENU_BG = "#1f2a3a"              # 菜单栏背景
MENU_BTN_BG = "#2a3b52"          # 按钮默认背景
MENU_BTN_ACTIVE_BG = "#3d5a80"   # 按钮高亮（当前页）背景
MENU_BTN_FG = "#ffffff"          # 按钮文字颜色
CONTENT_BG = "#f5f6fa"           # 内容区背景
CONTENT_TITLE_FG = "#1f2a3a"     # 标题文字颜色
CONTENT_HINT_FG = "#7a8699"      # 提示文字颜色
BTN_BG = "#3d5a80"               # 主按钮背景
BTN_FG = "#ffffff"               # 主按钮文字颜色

# 日志文本框最多显示的行数（防止内容过多导致界面卡顿）
MAX_LOG_LINES = 3000


def _format_size(num: int) -> str:
    """把字节数格式化为可读字符串（B/KB/MB/GB/TB）。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024


class PCMApp:
    """PCM 电脑优化器主窗口。"""

    # 页面标识 -> 显示标题 的映射（后续扩展具体功能页时在此追加）
    PAGES = {
        "disk_cleaner": "磁盘清理",
        "downloader": "多线程下载",
        "tools": "实用工具",
        "security": "渗透测试",
        "advanced": "高级功能",
    }

    def __init__(self, root: tk.Tk):
        """初始化主窗口：设置标题/尺寸/图标，并搭建左右布局。"""
        self.root = root
        self.menu_buttons = {}    # 页面标识 -> 按钮对象，用于高亮当前页
        self.current_page = None  # 当前显示的页面标识

        # ---- 工作线程 -> 主线程的消息队列与线程句柄 ----
        self._scan_queue = queue.Queue()
        self._scan_thread = None          # 磁盘清理：扫描线程
        self._clean_thread = None         # 磁盘清理：清理线程
        self._polling = False             # 队列轮询循环是否在运行
        self._scan_files = []             # 磁盘清理：最近一次扫描结果
        self._log_state = {}              # 每个文本框的行数/截断状态

        # ---- 磁盘清理页控件（切换页面后会被重建） ----
        self._cleaner_text = None
        self._cleaner_status = None
        self._cleaner_scan_btn = None

        # ---- 多线程下载页状态与控件 ----
        self._downloader = None           # 当前 Downloader 实例
        self._dl_url_var = None
        self._dl_path_var = None
        self._dl_threads_var = None
        self._dl_speed_var = None
        self._dl_progress = None
        self._dl_status = None
        self._dl_log = None
        self._dl_start_btn = None
        self._dl_pause_btn = None
        self._dl_resume_btn = None

        # ---- 窗口基本设置 ----
        root.title("PCM 电脑优化器")
        root.geometry("900x600")   # 默认大小 900x600
        root.minsize(760, 480)     # 最小尺寸，防止布局被压缩得太小
        root.configure(bg=CONTENT_BG)

        # ---- 设置窗口图标 ----
        try:
            icon_path = utils.ensure_icon()  # 获取（必要时生成）图标路径
            root.iconbitmap(icon_path)       # 设置窗口左上角图标
        except Exception as exc:
            # 图标设置失败不影响程序运行，仅打印提示
            print(f"[PCM] 设置窗口图标失败：{exc}")

        # ---- 搭建界面 ----
        self._build_layout()

        # ---- 默认显示第一个页面 ----
        self.switch_content("disk_cleaner")

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_layout(self):
        """搭建左侧菜单栏 + 右侧内容区。"""
        # ---- 左侧菜单栏（固定宽度 180，纵向铺满窗口） ----
        self.menu_frame = tk.Frame(self.root, width=180, bg=MENU_BG)
        self.menu_frame.pack(side="left", fill="y")
        # 禁止子控件撑大菜单栏，保持 180 宽
        self.menu_frame.pack_propagate(False)

        # 菜单顶部标题
        tk.Label(
            self.menu_frame,
            text="PCM",
            font=("Microsoft YaHei UI", 18, "bold"),
            bg=MENU_BG, fg="#ffffff",
        ).pack(pady=(24, 30))

        # 依次创建三个菜单按钮
        for page_key, page_title in self.PAGES.items():
            btn = tk.Button(
                self.menu_frame,
                text=page_title,
                font=("Microsoft YaHei UI", 11),
                bg=MENU_BTN_BG,
                fg=MENU_BTN_FG,
                activebackground=MENU_BTN_ACTIVE_BG,
                activeforeground=MENU_BTN_FG,
                relief="flat",        # 扁平风格按钮
                anchor="w",           # 文字左对齐
                padx=18, pady=10,
                cursor="hand2",
                # 点击时切换到对应页面（用默认参数固定 page_key，避免闭包陷阱）
                command=lambda key=page_key: self.switch_content(key),
            )
            btn.pack(fill="x", padx=10, pady=4)
            self.menu_buttons[page_key] = btn

        # 菜单底部版本信息
        tk.Label(
            self.menu_frame,
            text="v1.0.0",
            font=("Microsoft YaHei UI", 9),
            bg=MENU_BG, fg="#8fa3bf",
        ).pack(side="bottom", pady=10)

        # ---- 右侧内容区（Frame，占满剩余空间） ----
        self.content_frame = tk.Frame(self.root, bg=CONTENT_BG)
        self.content_frame.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------
    def switch_content(self, page_name: str):
        """
        切换右侧内容区显示的页面。

        :param page_name: 页面标识（见 PAGES 字典的键）
        """
        # 更新菜单按钮高亮：当前页按钮高亮，其余恢复默认
        for key, btn in self.menu_buttons.items():
            btn.configure(
                bg=MENU_BTN_ACTIVE_BG if key == page_name else MENU_BTN_BG
            )

        # 清空内容区已有控件，避免叠加
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.current_page = page_name

        if page_name == "disk_cleaner":
            page = self.create_disk_cleaner_page()
            page.pack(fill="both", expand=True)
        elif page_name == "downloader":
            page = self.create_downloader_page()
            page.pack(fill="both", expand=True)
        elif page_name == "tools":
            page = self.create_tools_page()
            page.pack(fill="both", expand=True)
        elif page_name == "security":
            page = self.create_security_page()
            page.pack(fill="both", expand=True)
        elif page_name == "advanced":
            page = self.create_advanced_page()
            page.pack(fill="both", expand=True)
        else:
            # 其他页面：暂只显示标题占位
            title = self.PAGES.get(page_name, page_name)
            tk.Label(
                self.content_frame,
                text=title,
                font=("Microsoft YaHei UI", 26, "bold"),
                bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
            ).pack(expand=True)
            tk.Label(
                self.content_frame,
                text="该功能正在开发中，敬请期待……",
                font=("Microsoft YaHei UI", 11),
                bg=CONTENT_BG, fg=CONTENT_HINT_FG,
            ).pack(pady=(8, 0))

    # ------------------------------------------------------------------
    # 通用日志辅助（供各功能页的结果文本框使用）
    # ------------------------------------------------------------------
    def _append_log(self, text_widget, message: str):
        """向指定文本框追加一行（带行数上限，防止卡顿）。"""
        if not (text_widget and text_widget.winfo_exists()):
            return
        key = id(text_widget)
        state = self._log_state.setdefault(key, {"lines": 0, "truncated": False})
        if state["truncated"]:
            return
        state["lines"] += 1
        text_widget.configure(state="normal")
        if state["lines"] > MAX_LOG_LINES:
            state["truncated"] = True
            text_widget.insert(
                "end", f"\n── 内容过多，仅显示前 {MAX_LOG_LINES} 行，其余省略 ──\n")
        else:
            text_widget.insert("end", message + "\n")
            text_widget.see("end")
        text_widget.configure(state="disabled")

    def _clear_log(self, text_widget):
        """清空指定文本框及其行数统计。"""
        if text_widget and text_widget.winfo_exists():
            text_widget.configure(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.configure(state="disabled")
        self._log_state.pop(id(text_widget), None)

    # ------------------------------------------------------------------
    # 磁盘清理页
    # ------------------------------------------------------------------
    def create_disk_cleaner_page(self) -> tk.Frame:
        """
        创建并返回磁盘清理功能页（Frame）。

        包含：说明文字、“开始扫描 / 清空结果”按钮、
        带滚动条的结果文本框、状态标签。
        """
        page = tk.Frame(self.content_frame, bg=CONTENT_BG)

        # 标题与说明
        tk.Label(
            page, text="磁盘清理",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        ).pack(pady=(18, 2))
        tk.Label(
            page, text="扫描系统临时目录、浏览器缓存与系统日志文件（回收站暂不处理）",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_HINT_FG,
        ).pack(pady=(0, 10))

        # 按钮行
        btn_row = tk.Frame(page, bg=CONTENT_BG)
        btn_row.pack(fill="x", padx=16)
        self._cleaner_scan_btn = tk.Button(
            btn_row, text="开始扫描", command=self._start_scan,
            font=("Microsoft YaHei UI", 11), bg=BTN_BG, fg=BTN_FG,
            activebackground=MENU_BTN_ACTIVE_BG, relief="flat",
            padx=16, pady=4, cursor="hand2",
        )
        self._cleaner_scan_btn.pack(side="left")
        tk.Button(
            btn_row, text="清空结果", command=self._clear_scan_result,
            font=("Microsoft YaHei UI", 11), bg="#aab4c4", fg="#1f2a3a",
            activebackground="#c3cbd8", relief="flat",
            padx=16, pady=4, cursor="hand2",
        ).pack(side="left", padx=(10, 0))

        # 结果文本框 + 滚动条
        text_frame = tk.Frame(page, bg=CONTENT_BG)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))
        self._cleaner_text = tk.Text(
            text_frame, wrap="none", state="disabled",
            bg="#ffffff", fg="#22303f", font=("Consolas", 9),
            relief="solid", bd=1,
        )
        scrollbar = tk.Scrollbar(text_frame, command=self._cleaner_text.yview)
        self._cleaner_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._cleaner_text.pack(side="left", fill="both", expand=True)

        # 状态标签
        self._cleaner_status = tk.Label(
            page, text="就绪", anchor="w",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        )
        self._cleaner_status.pack(fill="x", padx=16, pady=8)

        return page

    # ------------------------------------------------------------------
    # 磁盘清理：扫描 / 清理
    # ------------------------------------------------------------------
    def _start_scan(self):
        """点击“开始扫描”：在后台线程执行扫描，界面实时刷新。"""
        if self._scan_thread and self._scan_thread.is_alive():
            messagebox.showinfo("磁盘清理", "扫描正在进行中，请稍候……")
            return
        # 清空上次的扫描结果
        self._clear_log(self._cleaner_text)
        self._scan_files = []
        self._set_scan_button("disabled", "扫描中…")
        self._update_cleaner_status("正在扫描，请稍候……")

        self._scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._scan_thread.start()
        self._ensure_polling()

    def _scan_worker(self):
        """后台线程：执行扫描，结果通过队列回传主线程。"""
        try:
            cleaner = disk_cleaner.DiskCleaner(
                progress_callback=self._on_scan_progress)
            file_list, total_size = cleaner.scan()
            self._scan_queue.put(("scan_done", (file_list, total_size)))
        except Exception as exc:
            self._scan_queue.put(("error", f"扫描失败：{exc}"))
        finally:
            self._scan_thread = None

    def _on_scan_progress(self, count, size, message):
        """进度回调（在扫描线程中执行）：只入队，不直接操作界面。"""
        self._scan_queue.put(("progress", (count, size, message)))

    def _on_scan_finished(self, file_list, total_size):
        """扫描完成（主线程）：显示结果并询问是否清理。"""
        self._scan_files = file_list
        self._set_scan_button("normal", "开始扫描")
        summary = (f"扫描完成：发现 {len(file_list)} 项垃圾，"
                   f"共 {_format_size(total_size)}")
        self._update_cleaner_status(summary)
        self._append_log(self._cleaner_text, f"── {summary} ──")

        if not file_list:
            messagebox.showinfo("磁盘清理", "未发现可清理的垃圾文件。")
            return

        # 询问用户是否将垃圾移入回收站
        if messagebox.askyesno(
            "磁盘清理",
            f"发现 {len(file_list)} 项垃圾文件，共 {_format_size(total_size)}。\n\n"
            "确定将它们移动到回收站吗？",
        ):
            self._start_clean(file_list)

    def _start_clean(self, files):
        """在后台线程执行 clean()，把文件移动到回收站。"""
        self._set_scan_button("disabled", "清理中…")
        self._update_cleaner_status(f"正在将 {len(files)} 项移动到回收站……")
        self._clean_thread = threading.Thread(
            target=self._clean_worker, args=(files,), daemon=True)
        self._clean_thread.start()
        self._ensure_polling()

    def _clean_worker(self, files):
        """后台线程：执行清理，结果通过队列回传主线程。"""
        try:
            moved, failed = disk_cleaner.clean(files)
            self._scan_queue.put(("clean_done", (moved, failed)))
        except Exception as exc:
            self._scan_queue.put(("error", f"清理失败：{exc}"))
        finally:
            self._clean_thread = None

    def _on_clean_finished(self, moved, failed):
        """清理完成（主线程）：更新界面并弹窗提示。"""
        self._set_scan_button("normal", "开始扫描")
        if failed:
            msg = (f"清理完成：成功移动 {moved} 项到回收站，"
                   f"{failed} 项失败（可能被占用或无权限）。")
        else:
            msg = f"清理完成：已移动 {moved} 项到回收站。"
        self._update_cleaner_status(msg)
        self._append_log(self._cleaner_text, f"── {msg} ──")
        messagebox.showinfo("磁盘清理", msg)

    # ------------------------------------------------------------------
    # 多线程下载页
    # ------------------------------------------------------------------
    def create_downloader_page(self) -> tk.Frame:
        """
        创建并返回多线程下载功能页（Frame）。

        包含：URL / 保存路径 / 线程数 / 限速 输入，开始·暂停·继续按钮，
        进度条、日志文本框与状态标签。
        """
        page = tk.Frame(self.content_frame, bg=CONTENT_BG)

        # 标题与说明
        tk.Label(
            page, text="多线程下载",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        ).pack(pady=(18, 2))
        tk.Label(
            page, text="支持多线程分块下载、断点续传与限速（需安装 requests）",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_HINT_FG,
        ).pack(pady=(0, 10))

        # ---- 参数表单 ----
        self._dl_url_var = tk.StringVar()
        self._dl_path_var = tk.StringVar()
        self._dl_threads_var = tk.StringVar(value="4")
        self._dl_speed_var = tk.StringVar(value="")

        form = tk.Frame(page, bg=CONTENT_BG)
        form.pack(fill="x", padx=24)
        form.columnconfigure(1, weight=1)

        tk.Label(form, text="下载地址：", font=("Microsoft YaHei UI", 10),
                 bg=CONTENT_BG, fg=CONTENT_TITLE_FG
                 ).grid(row=0, column=0, sticky="w", pady=3)
        tk.Entry(form, textvariable=self._dl_url_var, font=("Consolas", 10)
                 ).grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)

        tk.Label(form, text="保存到：", font=("Microsoft YaHei UI", 10),
                 bg=CONTENT_BG, fg=CONTENT_TITLE_FG
                 ).grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(form, textvariable=self._dl_path_var, font=("Consolas", 10)
                 ).grid(row=1, column=1, sticky="ew", pady=3)
        tk.Button(form, text="浏览…", command=self._browse_save_path,
                  font=("Microsoft YaHei UI", 10), bg="#aab4c4",
                  activebackground="#c3cbd8", relief="flat", padx=10,
                  cursor="hand2").grid(row=1, column=2, padx=(8, 0), pady=3)

        # 线程数与限速（同一行）
        row2 = tk.Frame(form, bg=CONTENT_BG)
        row2.grid(row=2, column=1, columnspan=2, sticky="w", pady=3)
        tk.Label(row2, text="线程数：", font=("Microsoft YaHei UI", 10),
                 bg=CONTENT_BG, fg=CONTENT_TITLE_FG).pack(side="left")
        tk.Spinbox(row2, from_=1, to=16, textvariable=self._dl_threads_var,
                   width=5, font=("Consolas", 10)).pack(side="left")
        tk.Label(row2, text="   速度限制 (MB/s)：", font=("Microsoft YaHei UI", 10),
                 bg=CONTENT_BG, fg=CONTENT_TITLE_FG).pack(side="left")
        tk.Entry(row2, textvariable=self._dl_speed_var, width=8,
                 font=("Consolas", 10)).pack(side="left")
        tk.Label(row2, text="（留空不限速）", font=("Microsoft YaHei UI", 9),
                 bg=CONTENT_BG, fg=CONTENT_HINT_FG).pack(side="left")

        # ---- 控制按钮 ----
        btn_row = tk.Frame(page, bg=CONTENT_BG)
        btn_row.pack(fill="x", padx=24, pady=(8, 4))
        self._dl_start_btn = tk.Button(
            btn_row, text="开始下载", command=self._start_download,
            font=("Microsoft YaHei UI", 11), bg=BTN_BG, fg=BTN_FG,
            activebackground=MENU_BTN_ACTIVE_BG, relief="flat",
            padx=16, pady=4, cursor="hand2")
        self._dl_start_btn.pack(side="left")
        self._dl_pause_btn = tk.Button(
            btn_row, text="暂停", command=self._pause_download,
            font=("Microsoft YaHei UI", 11), bg="#e6a23c", fg="#ffffff",
            activebackground="#eebc6d", relief="flat",
            padx=16, pady=4, cursor="hand2", state="disabled")
        self._dl_pause_btn.pack(side="left", padx=(10, 0))
        self._dl_resume_btn = tk.Button(
            btn_row, text="继续", command=self._resume_download,
            font=("Microsoft YaHei UI", 11), bg="#67c23a", fg="#ffffff",
            activebackground="#8fd46f", relief="flat",
            padx=16, pady=4, cursor="hand2", state="disabled")
        self._dl_resume_btn.pack(side="left", padx=(10, 0))

        # ---- 进度条 ----
        self._dl_progress = ttk.Progressbar(page, mode="determinate", maximum=100)
        self._dl_progress.pack(fill="x", padx=24, pady=(4, 0))

        # ---- 日志文本框 + 滚动条 ----
        log_frame = tk.Frame(page, bg=CONTENT_BG)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(8, 0))
        self._dl_log = tk.Text(
            log_frame, wrap="none", state="disabled",
            bg="#ffffff", fg="#22303f", font=("Consolas", 9),
            relief="solid", bd=1,
        )
        scrollbar = tk.Scrollbar(log_frame, command=self._dl_log.yview)
        self._dl_log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._dl_log.pack(side="left", fill="both", expand=True)

        # ---- 状态标签 ----
        self._dl_status = tk.Label(
            page, text="就绪", anchor="w",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        )
        self._dl_status.pack(fill="x", padx=24, pady=8)

        self._refresh_dl_buttons()
        return page

    # ------------------------------------------------------------------
    # 多线程下载：控制
    # ------------------------------------------------------------------
    def _browse_save_path(self):
        """“浏览…”按钮：弹出保存对话框选择保存路径。"""
        path = filedialog.asksaveasfilename(
            title="选择保存位置",
            defaultextension="",
            filetypes=[("所有文件", "*.*")],
        )
        if path:
            self._dl_path_var.set(path)

    @staticmethod
    def _url_filename(url: str) -> str:
        """从 URL 中提取文件名（用于自动填充保存路径）。"""
        from urllib.parse import unquote, urlparse
        name = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
        return name

    def _start_download(self):
        """点击“开始下载”：校验参数、创建 Downloader 并启动。"""
        if self._downloader and self._downloader.is_busy():
            messagebox.showinfo("多线程下载", "下载正在进行中，请先暂停或等待完成。")
            return

        url = self._dl_url_var.get().strip()
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showerror("多线程下载", "请输入有效的 http(s) 下载地址。")
            return

        save_path = self._dl_path_var.get().strip()
        if not save_path:
            # 保存路径为空时尝试从 URL 自动识别文件名
            name = self._url_filename(url)
            if name:
                save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
                self._dl_path_var.set(save_path)
            else:
                messagebox.showerror("多线程下载", "无法从地址识别文件名，请手动填写保存路径。")
                return

        # 线程数（1~16）
        try:
            threads = int(self._dl_threads_var.get())
        except ValueError:
            threads = 4
        threads = max(1, min(threads, 16))

        # 限速（MB/s，可留空）
        speed_text = self._dl_speed_var.get().strip()
        speed = None
        if speed_text:
            try:
                speed = float(speed_text)
                if speed <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("多线程下载", "速度限制必须是正数（MB/s），或留空表示不限速。")
                return

        # 创建下载器并启动（回调通过队列转发到主线程）
        try:
            self._downloader = downloader.Downloader(
                url, save_path, threads=threads, speed_limit=speed,
                on_progress=self._on_dl_progress,
                on_status=self._on_dl_status,
            )
        except Exception as exc:
            messagebox.showerror("多线程下载", str(exc))
            return

        self._clear_log(self._dl_log)
        self._update_dl_status("正在启动下载……")
        self._downloader.start()
        self._ensure_polling()
        self._refresh_dl_buttons()

    def _pause_download(self):
        """点击“暂停”按钮。"""
        if self._downloader:
            self._downloader.pause()
            self._refresh_dl_buttons()

    def _resume_download(self):
        """点击“继续”按钮。"""
        if self._downloader:
            self._downloader.resume()
            self._refresh_dl_buttons()

    def _on_dl_progress(self, current, total):
        """下载进度回调（工作线程）：只入队。"""
        self._scan_queue.put(("dl_progress", (current, total)))

    def _on_dl_status(self, msg):
        """下载状态回调（工作线程）：只入队。"""
        self._scan_queue.put(("dl_status", msg))

    # ------------------------------------------------------------------
    # 实用工具页
    # ------------------------------------------------------------------
    def _add_tool_buttons(self, group, tools, columns=2):
        """在工具分组 Frame 中按网格添加工具按钮。"""
        for i in range(columns):
            group.columnconfigure(i, weight=1)
        for idx, (label, func) in enumerate(tools):
            row, col = divmod(idx, columns)
            tk.Button(
                group, text=label,
                # 用默认参数固定 func，避免闭包陷阱；传入主窗口作为 parent
                command=lambda f=func: f(self.root),
                font=("Microsoft YaHei UI", 12), bg=BTN_BG, fg=BTN_FG,
                activebackground=MENU_BTN_ACTIVE_BG, relief="flat",
                pady=14, cursor="hand2",
            ).grid(row=row, column=col, sticky="nsew", padx=6, pady=6)

    def create_tools_page(self) -> tk.Frame:
        """创建并返回实用工具页（Frame）：四个工具分组，内容可滚动。"""
        page = tk.Frame(self.content_frame, bg=CONTENT_BG)

        tk.Label(
            page, text="实用工具",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        ).pack(pady=(18, 2))
        tk.Label(
            page, text="点击按钮打开对应工具（部分工具需要管理员权限、网络连接或额外依赖）",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_HINT_FG,
        ).pack(pady=(0, 8))

        # ---- 可滚动容器（工具较多，避免超出窗口高度） ----
        canvas = tk.Canvas(page, bg=CONTENT_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=CONTENT_BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        # 鼠标滚轮（仅当指针位于工具页内时生效）
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        # ---- 四个工具分组 ----
        groups = [
            ("系统工具", [
                ("计算器", tools_system.calc),
                ("系统信息", tools_system.sysinfo),
                ("电源控制", tools_system.power_control),
                ("进程管理器", tools_system.process_manager),
                ("Hosts 编辑器", tools_system.hosts_editor),
                ("磁盘测速", tools_system.disk_speed_test),
                ("批量重命名", tools_system.batch_rename),
                ("MD5 校验", tools_system.md5_checker),
                ("创建还原点", tools_system.restore_point),
                ("启动项管理", tools_system.startup_manager),
            ]),
            ("网络工具", [
                ("网速测试", tools_network.speed_test),
                ("IP 查询", tools_network.ip_query),
                ("Ping 测试", tools_network.ping_tool),
                ("端口扫描", tools_network.port_scanner),
                ("Wi-Fi 密码", tools_network.wifi_password),
            ]),
            ("图像媒体", [
                ("图片格式转换", tools_media.image_convert),
                ("图片压缩", tools_media.image_compress),
                ("屏幕截图", tools_media.screenshot),
                ("简易绘图板", tools_media.draw_board),
                ("二维码生成", tools_media.qr_generator),
            ]),
            ("文本办公", [
                ("文本差异对比", tools_text.text_diff),
                ("JSON 工具", tools_text.json_tool),
                ("时间戳转换", tools_text.timestamp_convert),
                ("颜色拾取", tools_text.color_picker),
                ("单位换算", tools_text.unit_convert),
                ("随机密码", tools_text.password_gen),
            ]),
        ]
        for group_title, tools in groups:
            group = tk.LabelFrame(
                inner, text=group_title, font=("Microsoft YaHei UI", 11, "bold"),
                bg=CONTENT_BG, fg=CONTENT_TITLE_FG, padx=8, pady=6,
            )
            group.pack(fill="x", padx=12, pady=(0, 6))
            self._add_tool_buttons(group, tools)

        return page

    # ------------------------------------------------------------------
    # 渗透测试页
    # ------------------------------------------------------------------
    def create_security_page(self) -> tk.Frame:
        """创建并返回渗透测试页（Frame）：10 个网络安全工具按钮。"""
        page = tk.Frame(self.content_frame, bg=CONTENT_BG)

        tk.Label(
            page, text="渗透测试",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        ).pack(pady=(18, 2))
        tk.Label(
            page, text="网络安全诊断工具（仅限授权测试，请遵守法律法规）",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_HINT_FG,
        ).pack(pady=(0, 10))

        group = tk.LabelFrame(
            page, text="安全测试工具", font=("Microsoft YaHei UI", 11, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG, padx=8, pady=6,
        )
        group.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self._add_tool_buttons(group, [
            ("端口扫描器", tools_security.port_scan),
            ("主机发现", tools_security.subnet_scan),
            ("路由追踪", tools_security.traceroute),
            ("WHOIS 查询", tools_security.whois_lookup),
            ("DNS 查询", tools_security.dns_lookup),
            ("HTTP 安全头", tools_security.http_header),
            ("密码强度", tools_security.password_strength),
            ("哈希工具", tools_security.hash_tools),
            ("IP 归属地", tools_security.ip_geo),
            ("连接状态", tools_security.net_stat),
        ])

        return page

    # ------------------------------------------------------------------
    # 高级功能页
    # ------------------------------------------------------------------
    def create_advanced_page(self) -> tk.Frame:
        """创建并返回高级功能页（Frame）：五个分组，内容可滚动。"""
        page = tk.Frame(self.content_frame, bg=CONTENT_BG)

        tk.Label(
            page, text="高级功能",
            font=("Microsoft YaHei UI", 20, "bold"),
            bg=CONTENT_BG, fg=CONTENT_TITLE_FG,
        ).pack(pady=(18, 2))
        tk.Label(
            page, text="系统增强 / 硬件监控 / 文件管理 / 开发工具 / 娱乐扩展",
            font=("Microsoft YaHei UI", 10),
            bg=CONTENT_BG, fg=CONTENT_HINT_FG,
        ).pack(pady=(0, 8))

        # 可滚动容器
        canvas = tk.Canvas(page, bg=CONTENT_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=CONTENT_BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        groups = [
            ("系统增强", [
                ("上帝模式/开发者", tools_advanced.god_mode),
                ("内存监控", tools_advanced.memory_monitor),
                ("服务管理", tools_advanced.service_manager),
                ("右键菜单管理", tools_advanced.context_menu),
                ("隐私清理", tools_advanced.privacy_cleaner),
                ("系统一键修复", tools_advanced.system_repair),
            ]),
            ("硬件监控", [
                ("硬件信息", tools_advanced.hardware_info),
                ("性能压力测试", tools_advanced.stress_test),
                ("磁盘健康", tools_advanced.disk_health),
            ]),
            ("文件管理", [
                ("重复文件查找", tools_advanced.dup_finder),
                ("大文件分析", tools_advanced.big_files),
                ("安全删除", tools_advanced.secure_wipe),
                ("软件卸载管理", tools_advanced.uninstall_manager),
            ]),
            ("开发工具", [
                ("编码解码", tools_advanced.codec_tools),
                ("文本加解密", tools_advanced.text_crypto),
                ("正则测试", tools_advanced.regex_tester),
                ("XML 工具", tools_advanced.xml_tool),
                ("文本处理", tools_advanced.text_processor),
            ]),
            ("娱乐扩展", [
                ("屏幕录制 GIF", tools_advanced.gif_recorder),
                ("鼠标连点器", tools_advanced.auto_clicker),
            ]),
        ]
        for group_title, tools in groups:
            group = tk.LabelFrame(
                inner, text=group_title, font=("Microsoft YaHei UI", 11, "bold"),
                bg=CONTENT_BG, fg=CONTENT_TITLE_FG, padx=8, pady=6,
            )
            group.pack(fill="x", padx=12, pady=(0, 6))
            self._add_tool_buttons(group, tools)

        return page

    # ------------------------------------------------------------------
    # 工作线程消息轮询（在主线程中执行）
    # ------------------------------------------------------------------
    def _ensure_polling(self):
        """确保队列轮询循环已启动（有工作线程时调用）。"""
        if not self._polling:
            self._polling = True
            self.root.after(100, self._poll_worker_messages)

    def _poll_worker_messages(self):
        """轮询工作线程回传的消息并刷新界面。"""
        try:
            while True:
                kind, payload = self._scan_queue.get_nowait()
                if kind == "progress":
                    count, size, message = payload
                    self._append_log(self._cleaner_text, message)
                    self._update_cleaner_status(
                        f"正在扫描……已发现 {count} 项，共 {_format_size(size)}")
                elif kind == "scan_done":
                    file_list, total_size = payload
                    self._on_scan_finished(file_list, total_size)
                elif kind == "clean_done":
                    moved, failed = payload
                    self._on_clean_finished(moved, failed)
                elif kind == "dl_progress":
                    current, total = payload
                    self._update_dl_progress(current, total)
                elif kind == "dl_status":
                    self._append_log(self._dl_log, payload)
                    self._update_dl_status(payload)
                    self._refresh_dl_buttons()
                elif kind == "error":
                    self._set_scan_button("normal", "开始扫描")
                    self._update_cleaner_status(payload)
                    messagebox.showerror("PCM", payload)
        except queue.Empty:
            pass

        # 队列中还有消息或仍有任务在运行，则继续轮询
        if (not self._scan_queue.empty()
                or self._scan_thread is not None
                or self._clean_thread is not None
                or (self._downloader is not None and self._downloader.is_busy())):
            self.root.after(100, self._poll_worker_messages)
        else:
            self._polling = False

    # ------------------------------------------------------------------
    # 下载页界面辅助方法
    # ------------------------------------------------------------------
    def _update_dl_progress(self, current, total):
        """根据进度更新进度条与状态标签。"""
        try:
            if self._dl_progress and self._dl_progress.winfo_exists():
                if total and total > 0:
                    self._dl_progress.stop()
                    self._dl_progress.configure(mode="determinate", maximum=total)
                    self._dl_progress.configure(value=current)
                else:
                    self._dl_progress.configure(mode="indeterminate", maximum=100)
                    self._dl_progress.start(50)
        except tk.TclError:
            pass
        if total and current < total:
            pct = current / total * 100
            self._update_dl_status(
                f"下载中：{_format_size(current)} / {_format_size(total)}"
                f"（{pct:.1f}%）")
        # current >= total 时保留状态标签（如“下载完成：…”），不再覆盖

    def _update_dl_status(self, message: str):
        """更新下载页状态标签（页面已销毁时安全忽略）。"""
        try:
            if self._dl_status and self._dl_status.winfo_exists():
                self._dl_status.configure(text=message)
        except tk.TclError:
            pass

    def _refresh_dl_buttons(self):
        """根据下载器状态刷新 开始/暂停/继续 按钮可用性。"""
        state = self._downloader.state if self._downloader else "idle"
        try:
            if self._dl_start_btn and self._dl_start_btn.winfo_exists():
                self._dl_start_btn.configure(
                    state="normal" if state in ("idle", "finished", "error", "stopped")
                    else "disabled")
            if self._dl_pause_btn and self._dl_pause_btn.winfo_exists():
                self._dl_pause_btn.configure(
                    state="normal" if state in ("running", "starting") else "disabled")
            if self._dl_resume_btn and self._dl_resume_btn.winfo_exists():
                self._dl_resume_btn.configure(
                    state="normal" if state == "paused" else "disabled")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 磁盘清理页界面辅助方法
    # ------------------------------------------------------------------
    def _clear_scan_result(self):
        """“清空结果”按钮：清空文本框并复位状态。"""
        if self._scan_thread or self._clean_thread:
            messagebox.showinfo("磁盘清理", "任务正在进行中，暂不能清空。")
            return
        self._clear_log(self._cleaner_text)
        self._scan_files = []
        self._update_cleaner_status("就绪")

    def _update_cleaner_status(self, message: str):
        """更新磁盘清理页状态标签（页面已销毁时安全忽略）。"""
        try:
            if self._cleaner_status and self._cleaner_status.winfo_exists():
                self._cleaner_status.configure(text=message)
        except tk.TclError:
            pass

    def _set_scan_button(self, state: str, text: str):
        """设置“开始扫描”按钮状态（页面已销毁时安全忽略）。"""
        try:
            if self._cleaner_scan_btn and self._cleaner_scan_btn.winfo_exists():
                self._cleaner_scan_btn.configure(state=state, text=text)
        except tk.TclError:
            pass
