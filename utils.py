# -*- coding: utf-8 -*-
"""
utils.py —— 通用工具模块

提供 ensure_icon() 函数：
    检测程序所在目录下是否存在 app.ico 图标文件；
    若不存在，则生成一个 256x256 的深蓝色图标
    （背景 RGB(0,30,60)，白色粗体 "PCM" 文字居中），并保存为 app.ico。

生成方式（按优先级）：
    1. 优先使用 Pillow 绘制（支持系统粗体字体，效果最好）；
    2. 若未安装 Pillow，则退回纯标准库方案：用 zlib/struct 手写
       PNG + ICO 文件，并用内置的 5x7 点阵字库画出 "PCM" 文字，
       保证程序在任意环境都能正常运行。
"""
import os
import struct
import zlib

# ---------- 图标相关常量 ----------
ICON_SIZE = 256                    # 图标边长（像素）
ICON_BG_COLOR = (0, 30, 60)        # 深蓝色背景
ICON_TEXT = "PCM"                  # 图标上的文字
ICON_TEXT_COLOR = (255, 255, 255)  # 白色文字

# 依次尝试的粗体字体文件（Windows 常见字体路径）
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
    r"C:\Windows\Fonts\msyhbd.ttc",     # 微软雅黑 Bold
    r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
]

# 兜底方案用：内置 5x7 点阵字库（1 为前景色，0 为背景色）
_BITMAP_FONT = {
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
}


# ----------------------------------------------------------------------
# 方案一：Pillow 绘制（首选）
# ----------------------------------------------------------------------
def _make_icon_with_pillow(icon_path: str):
    """
    使用 Pillow 生成图标并保存。

    注意：Pillow 的导入放在函数内部，这样即使未安装 Pillow，
    模块本身也能被正常导入，程序可继续运行。
    """
    from PIL import Image, ImageDraw, ImageFont  # 延迟导入

    # 1) 创建深蓝色画布
    image = Image.new("RGB", (ICON_SIZE, ICON_SIZE), ICON_BG_COLOR)
    draw = ImageDraw.Draw(image)

    # 2) 加载粗体字体（字号取图标尺寸的 45% 左右，视觉上比较协调）
    font = _load_bold_font(int(ICON_SIZE * 0.45))

    # 3) 计算文字实际占用的区域，实现水平、垂直方向都居中
    #    （手动计算包围盒，不依赖 libraqm，兼容性更好）
    bbox = draw.textbbox((0, 0), ICON_TEXT, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (ICON_SIZE - text_width) // 2 - bbox[0]
    y = (ICON_SIZE - text_height) // 2 - bbox[1]

    # 4) 绘制白色粗体文字
    draw.text((x, y), ICON_TEXT, fill=ICON_TEXT_COLOR, font=font)

    # 5) 保存为 ICO 格式（同时写入 256x256 尺寸）
    image.save(icon_path, format="ICO", sizes=[(ICON_SIZE, ICON_SIZE)])


def _load_bold_font(size: int):
    """加载一个指定大小的粗体字体；全部失败时退回 Pillow 默认字体。"""
    from PIL import ImageFont

    for font_path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            # 该字体不存在，尝试下一个候选
            continue
    # 找不到系统字体时使用内置默认字体（无粗体效果，仅作兜底）
    return ImageFont.load_default()


# ----------------------------------------------------------------------
# 方案二：纯标准库兜底（未安装 Pillow 时使用）
# ----------------------------------------------------------------------
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """构造一个 PNG 数据块（长度 + 类型 + 数据 + CRC32）。"""
    chunk = tag + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def _make_icon_without_pillow(icon_path: str):
    """
    不使用任何第三方库生成图标：
        1. 用内置 5x7 点阵字库绘制 "PCM"，放大后写入 RGB 像素；
        2. 按 PNG 规范用 zlib 压缩成 PNG 数据；
        3. 将 PNG 嵌入 ICO 容器（Windows Vista 及以上支持 PNG 压缩的 ICO）。
    """
    scale = 8                     # 点阵字放大倍数
    letter_w = 5 * scale          # 单个字符宽度
    letter_h = 7 * scale          # 单个字符高度
    letter_gap = 2 * scale        # 字符间距
    text_w = len(ICON_TEXT) * letter_w + (len(ICON_TEXT) - 1) * letter_gap
    start_x = (ICON_SIZE - text_w) // 2    # 文字起始 x
    start_y = (ICON_SIZE - letter_h) // 2  # 文字起始 y

    # 逐行生成 RGB 像素（每行最前面补 1 字节 PNG 滤波类型 0）
    raw = bytearray()
    for y in range(ICON_SIZE):
        raw.append(0)  # filter: None
        for x in range(ICON_SIZE):
            color = ICON_BG_COLOR
            # 判断 (x, y) 是否落在某个字符的实心点上（需同时满足 x、y 都在文字范围内）
            for i, ch in enumerate(ICON_TEXT):
                left = start_x + i * (letter_w + letter_gap)
                if (left <= x < left + letter_w
                        and start_y <= y < start_y + letter_h):
                    fx = (x - left) // scale
                    fy = (y - start_y) // scale
                    if _BITMAP_FONT[ch][fy][fx] == "1":
                        color = ICON_TEXT_COLOR
                        break
            raw += bytes(color)

    # 组装 PNG 文件（8 位 RGB，非隔行）
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(
        ">IIBBBBB", ICON_SIZE, ICON_SIZE, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
    png += _png_chunk(b"IEND", b"")

    # 将 PNG 嵌入 ICO：文件头(6字节) + 目录项(16字节) + PNG 数据
    # 目录项中宽/高为 0 表示 256，位深 32，数据偏移 = 6 + 16 = 22
    ico = struct.pack("<HHH", 0, 1, 1)                                  # ICONDIR
    ico += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)    # ICONDIRENTRY
    ico += png

    with open(icon_path, "wb") as f:
        f.write(ico)


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
def ensure_icon() -> str:
    """
    确保 app.ico 图标存在，返回其完整路径。

    流程：
        1. 检查图标是否已存在（存在则直接返回路径，避免重复生成）；
        2. 不存在则优先用 Pillow 生成；未安装 Pillow 时用纯标准库兜底。
    """
    # 图标固定在 utils.py 所在目录，避免“当前工作目录”变化导致找不到图标
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")

    # 已存在则直接返回
    if os.path.exists(icon_path):
        return icon_path

    # 尝试 Pillow 方案，未安装时自动降级
    try:
        _make_icon_with_pillow(icon_path)
    except ImportError:
        # Pillow 未安装：使用纯标准库兜底方案
        _make_icon_without_pillow(icon_path)

    return icon_path


if __name__ == "__main__":
    # 便于单独测试：运行 python utils.py 即可生成/确认图标
    print("图标路径：", ensure_icon())
