# -*- coding: utf-8 -*-
"""
OCR 小软件 —— 应用图标生成脚本

用代码绘制图标（而非外部设计文件），保证可复现：
任何人跑一次本脚本，都能得到完全相同的图标。

输出：
    assets/icon.ico   多尺寸 Windows 图标（16/24/32/48/64/128/256）
    assets/icon.png   256×256 PNG（供 README / 非 Windows 平台使用）

设计：蓝色渐变圆角方块 + 白色「扫描取景框 + 文字横线」，
表达「从图像里提取文字」这一核心动作。

用法：
    .venv/Scripts/python.exe assets/make_icon.py
"""
import io
import os
import struct

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

# 主题色：蓝色渐变（浅 -> 深）
TOP = (59, 130, 246)        # #3B82F6
BOTTOM = (29, 78, 216)      # #1D4ED8
WHITE = (255, 255, 255, 255)

SIZES = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4             # 超采样倍数：先在 4 倍画布上绘制，再缩小，边缘更干净


def _lerp(a, b, t):
    """颜色线性插值"""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    """生成圆角矩形遮罩"""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _draw_corners(d: ImageDraw.ImageDraw, S: int, margin: float, arm: float, lw: int):
    """画四角取景框括号（扫描框的四个直角）"""
    x0, y0 = margin, margin
    x1, y1 = S - margin, S - margin
    corners = [
        [(x0, y0 + arm), (x0, y0), (x0 + arm, y0)],       # 左上
        [(x1 - arm, y0), (x1, y0), (x1, y0 + arm)],       # 右上
        [(x0, y1 - arm), (x0, y1), (x0 + arm, y1)],       # 左下
        [(x1 - arm, y1), (x1, y1), (x1, y1 - arm)],       # 右下
    ]
    for pts in corners:
        d.line(pts, fill=WHITE, width=lw, joint="curve")


def render(size: int) -> Image.Image:
    """渲染指定尺寸的图标（内部 4 倍超采样）。

    极小尺寸（<= 24px）走简化分支：只保留加粗的取景框轮廓，
    省略框内横线 —— 否则细节会糊成一团，反而看不清。
    """
    S = size * SUPERSAMPLE

    # ---- 背景：垂直渐变 + 圆角 ----
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        grad.putpixel((0, y), _lerp(TOP, BOTTOM, y / max(1, S - 1)))
    grad = grad.resize((S, S))

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), _rounded_mask(S, int(S * 0.22)))
    d = ImageDraw.Draw(img)

    if size <= 24:
        # ---- 小尺寸：只留取景框轮廓，加粗、放大，保证可辨识 ----
        _draw_corners(d, S, margin=S * 0.22, arm=S * 0.21,
                      lw=max(2, int(round(S * 0.095))))
    else:
        # ---- 标准尺寸：取景框 + 框内文字横线 ----
        lw = max(2, int(round(S * 0.058)))
        _draw_corners(d, S, margin=S * 0.24, arm=S * 0.115, lw=lw)

        # 横线在 y=0.435/0.575，该高度上取景框只占 x≈0.23~0.29 的竖直臂，
        # 因此横线可以放心延到 0.35~0.65，两侧仍留出空隙
        lx0, lx1 = S * 0.35, S * 0.65
        d.line([(lx0, S * 0.435), (lx1, S * 0.435)], fill=WHITE, width=lw)
        d.line([(lx0, S * 0.575), (S * 0.58, S * 0.575)], fill=WHITE, width=lw)

    return img.resize((size, size), Image.LANCZOS)


def save_ico(images, path: str):
    """把多张正方形图打包成 .ico。

    每个尺寸单独渲染（而不是从大图缩放），小尺寸更清晰；
    内部直接嵌入 PNG 数据（Windows Vista 及以上支持）。
    """
    pngs = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        pngs.append(buf.getvalue())

    n = len(pngs)
    header = struct.pack("<HHH", 0, 1, n)          # reserved, type=icon, count
    offset = 6 + 16 * n
    entries = b""
    for im, data in zip(images, pngs):
        w = 0 if im.width >= 256 else im.width     # 256 记作 0
        h = 0 if im.height >= 256 else im.height
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)

    with open(path, "wb") as f:
        f.write(header + entries + b"".join(pngs))


def main():
    images = [render(s) for s in SIZES]

    ico_path = os.path.join(HERE, "icon.ico")
    save_ico(images, ico_path)

    png_path = os.path.join(HERE, "icon.png")
    images[-1].save(png_path)                      # 256×256

    print("图标已生成：")
    print(f"  {ico_path}   （{len(SIZES)} 个尺寸：{SIZES}）")
    print(f"  {png_path}  （256×256）")


if __name__ == "__main__":
    main()
