# -*- coding: utf-8 -*-
"""
OCR 小软件 —— 阶段一：核心识别脚本（原型验证）

用途：在命令行跑通「图片 → 文本」，验证 PaddleOCR 能正常安装和识别。
用法：
    .venv/Scripts/python.exe test/test_ocr.py <图片路径>

示例：
    .venv/Scripts/python.exe test/test_ocr.py test_image.png
"""
import sys
from paddleocr import PaddleOCR


def recognize(image_path: str):
    # PaddleOCR 3.x 新版 API：用 *_model_name 指定轻量模型（mobile 系列）
    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",      # 轻量检测模型
        text_recognition_model_name="PP-OCRv5_mobile_rec",    # 轻量识别模型
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    # 3.x 用 predict() 方法
    result = ocr.predict(input=image_path)

    print("=" * 50)
    print(f"识别结果：{image_path}")
    print("=" * 50)

    # predict 返回 list，每个元素是 Result 对象
    for res in result:
        # res["rec_texts"] 是识别文本列表（每行一条）
        rec_texts = res.get("rec_texts", [])

        if not rec_texts:
            print("（未识别到文字）")
            continue

        # 只输出文本本身，不输出置信度
        for text in rec_texts:
            print(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：.venv/Scripts/python.exe test/test_ocr.py <图片路径>")
        sys.exit(1)

    recognize(sys.argv[1])
