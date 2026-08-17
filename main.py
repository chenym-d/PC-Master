# -*- coding: utf-8 -*-
"""
main.py —— 程序入口

启动 PCM 电脑优化器：
    1. 创建 Tk 根窗口；
    2. 用 PCMApp 初始化主界面；
    3. 进入 Tk 事件循环。
"""
import tkinter as tk

from gui import PCMApp


def main():
    """程序主函数：创建主窗口并进入事件循环。"""
    root = tk.Tk()      # 创建 Tk 根窗口
    app = PCMApp(root)  # 初始化主界面（保留引用，防止被垃圾回收）
    root.mainloop()     # 进入 Tk 事件循环


if __name__ == "__main__":
    main()
