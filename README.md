# PC-Master

一个基于 Python + Tkinter 的 Windows 全能电脑优化工具箱。

## 功能特色

-  **磁盘垃圾清理**：一键清理 C/D 盘临时文件、浏览器缓存、系统日志
-  **多线程下载器**：支持断点续传、自定义线程数（1-16）和速度限制
-  **26 个实用小工具**：涵盖系统管理、网络工具、图像处理、文本办公等领域

## 技术栈

- Python 3.10+
- Tkinter（GUI）
- Pillow（图像处理）
- PyInstaller（打包成 exe）

## 快速开始

### 直接运行 exe
从 [Releases](../../releases) 下载 `PCM.exe`，双击即可运行（部分功能需要管理员权限）。

### 从源码运行
```bash
pip install pillow psutil pywin32 requests speedtest-cli netifaces pyqrcode pypng send2trash
python main.py
