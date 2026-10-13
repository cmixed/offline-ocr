# -*- coding: utf-8 -*-
"""
OCR 小软件 —— 可视化脚本

用途：把识别结果（检测框 + 文字）画回原图，生成一张可视化结果图，
      直观看到「识别到了什么、在哪里」。

注意：用 PIL 绘制中文（cv2.putText 不支持中文，会显示成 ???）

用法：
    .venv/Scripts/python.exe test/visualize_ocr.py <图片路径> [输出路径]

示例：
    .venv/Scripts/python.exe test/visualize_ocr.py test_image.png
    （默认输出 result_vis.jpg）
"""
import sys
import os
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont
import numpy as np


def load_font(size=24):
    """加载中文字体，失败则用默认字体"""
    for font_path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def visualize(image_path: str, output_path: str = "result_vis.jpg"):
    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    result = ocr.predict(input=image_path)

    # 用 PIL 打开原图（RGB）
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = load_font(24)

    total = 0
    for res in result:
        rec_texts = res.get("rec_texts", [])
        rec_polys = res.get("rec_polys", None)
        if rec_polys is None:
            rec_polys = res.get("dt_polys", [])

        for i, text in enumerate(rec_texts):
            total += 1
            if i < len(rec_polys):
                poly = [tuple(map(float, p)) for p in rec_polys[i]]
                # 画检测框（绿色）
                draw.polygon(poly, outline=(0, 200, 0), width=3)
                # 在框上方标注文字（红色，只标文本本身）
                x, y = poly[0]
                draw.text((x, y - 30), text, fill=(220, 0, 0), font=font)

    img.save(output_path)
    print(f"共识别 {total} 处文字")
    print(f"可视化结果已保存：{os.path.abspath(output_path)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：.venv/Scripts/python.exe test/visualize_ocr.py <图片路径> [输出路径]")
        sys.exit(1)

    img_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "result_vis.jpg"
    visualize(img_path, out_path)
