# -*- coding: utf-8 -*-
"""
OCR 边界场景测试

覆盖五类场景：
1. 正常图片 —— 7 行混合内容，应全部识别
2. 无文字图片 —— 纯色图，应返回 0 行且不报错
3. 损坏文件 —— 伪造的 jpg，应抛出可读异常而非崩溃
4. 超大图 —— 超过 MAX_SIDE 应自动压缩，且框坐标还原到原图范围
5. 中文路径 —— 目录名与文件名均含中文，应正常识别

用法：
    .venv/Scripts/python.exe test/test_edge_cases.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from PIL import Image, ImageDraw, ImageFont          # noqa: E402

from ocr_engine import MAX_SIDE, OCREngine           # noqa: E402

_results = []


def check(name: str, ok: bool, detail: str = ""):
    _results.append(ok)
    flag = "通过" if ok else "失败"
    print(f"[{flag}] {name}" + (f" —— {detail}" if detail else ""))


def make_font(size: int):
    for p in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> int:
    engine = OCREngine()
    tmp = tempfile.gettempdir()

    # ---- 1. 正常图片 ----
    demo = os.path.join(HERE, "test_demo.png")
    lines = engine.recognize(demo)
    check("正常图片识别", len(lines) == 7, f"识别到 {len(lines)} 行")

    # ---- 2. 无文字图片 ----
    blank = os.path.join(tmp, "ocr_blank.png")
    Image.new("RGB", (600, 300), "white").save(blank)
    lines = engine.recognize(blank)
    check("无文字图片", len(lines) == 0, f"识别到 {len(lines)} 行（预期 0）")

    # ---- 3. 损坏文件 ----
    broken = os.path.join(tmp, "ocr_broken.jpg")
    with open(broken, "wb") as f:
        f.write(b"this is definitely not an image")
    try:
        engine.recognize(broken)
        check("损坏文件报错", False, "未抛出任何异常")
    except ValueError as e:
        check("损坏文件报错", True, f"抛出 ValueError：{str(e)[:36]}…")
    except Exception as e:                            # noqa: BLE001
        check("损坏文件报错", False, f"抛出了非预期异常 {type(e).__name__}")

    # ---- 4. 超大图 ----
    big_w, big_h = MAX_SIDE + 2460, 3600              # 6460 × 3600
    big = Image.new("RGB", (big_w, big_h), "white")
    ImageDraw.Draw(big).text(
        (200, 200), "超大图测试 BIG IMAGE 2026",
        fill="black", font=make_font(120))
    big_path = os.path.join(tmp, "ocr_big.png")
    big.save(big_path)

    lines = engine.recognize(big_path)
    in_range = bool(lines) and all(
        all(0 <= p[0] <= big_w and 0 <= p[1] <= big_h for p in line.box)
        for line in lines if line.box
    )
    check("超大图自动压缩", len(lines) >= 1 and in_range,
          f"识别到 {len(lines)} 行，框坐标在原图范围内：{in_range}")

    # ---- 5. 中文路径 ----
    cn_dir = os.path.join(tmp, "OCR 中文 目录")
    os.makedirs(cn_dir, exist_ok=True)
    cn_path = os.path.join(cn_dir, "测试图 中文.png")
    Image.open(demo).save(cn_path)
    lines = engine.recognize(cn_path)
    check("中文路径图片", len(lines) == 7, f"识别到 {len(lines)} 行")

    # ---- 清理临时文件 ----
    for p in (blank, broken, big_path):
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree(cn_dir, ignore_errors=True)

    # ---- 汇总 ----
    passed = sum(1 for ok in _results if ok)
    print()
    print(f"===== 结果：{passed}/{len(_results)} 项通过 =====")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
