# -*- coding: utf-8 -*-
"""格式支持测试：验证所有声明支持的图片格式都能「载入 + 识别」。

用途：
- 开发者改动了 SUPPORTED_EXTS 或读图逻辑后，跑一遍确认没有回归
- 贡献者可据此确认自己的环境正常

用法：
    .venv\\Scripts\\python.exe test\\test_formats.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PIL import Image, ImageDraw, ImageFont

from ocr_engine import OCREngine, SUPPORTED_EXTS, is_supported_ext

# 扩展名 -> PIL 保存格式（部分格式共用同一个编码器）
SAVE_FORMAT = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG",
    ".bmp": "BMP", ".webp": "WEBP", ".tif": "TIFF", ".tiff": "TIFF",
    ".gif": "GIF", ".ico": "ICO", ".tga": "TGA",
    ".ppm": "PPM", ".pgm": "PPM", ".pbm": "PPM", ".pnm": "PPM",
}

KEYWORD = "格式测试"          # 识别结果里应包含的关键字
TMP_DIR = os.path.join(ROOT, "test", "_fmt_tmp")


def make_sample() -> Image.Image:
    """造一张内容统一的测试图"""
    img = Image.new("RGB", (700, 160), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 42)
    except OSError:
        font = ImageFont.load_default()
    draw.text((30, 50), f"{KEYWORD} ABC 123", fill="black", font=font)
    return img


def main() -> int:
    os.makedirs(TMP_DIR, exist_ok=True)
    sample = make_sample()

    # 生成各格式样本
    samples = []
    skipped = []
    for ext in SUPPORTED_EXTS:
        fmt = SAVE_FORMAT.get(ext)
        if not fmt:
            skipped.append(ext)      # xbm / xpm 等 PIL 无法从 RGB 直接导出
            continue
        path = os.path.join(TMP_DIR, f"sample{ext}")
        try:
            sample.save(path, format=fmt)
            samples.append((ext, path))
        except OSError as e:
            skipped.append(f"{ext}({e})")

    print("=" * 60)
    print(f"格式支持测试：共 {len(SUPPORTED_EXTS)} 种扩展名，"
          f"生成样本 {len(samples)} 个，跳过 {len(skipped)} 个")
    if skipped:
        print(f"跳过（PIL 无法从 RGB 导出，但仍支持读取）：{', '.join(skipped)}")
    print("=" * 60)

    engine = OCREngine()

    # ---- 路径 1：引擎识别 ----
    print("\n[1] 引擎识别（PIL 解码 -> PaddleOCR）")
    ok_ocr = 0
    for ext, path in samples:
        try:
            lines = engine.recognize(path)
            text = "".join(line.text for line in lines)
            hit = KEYWORD in text
            ok_ocr += hit
            flag = "通过" if hit else "失败"
            print(f"  [{flag}] {ext:<6} {text or '(未识别到文字)'}")
        except Exception as e:                        # noqa: BLE001
            print(f"  [失败] {ext:<6} {type(e).__name__}: {e}")

    # ---- 路径 2：GUI 载入 ----
    print("\n[2] GUI 载入（PIL -> QPixmap，确认「能显示 = 能识别」）")
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)                      # noqa: F841
    import main as gui

    ok_gui = 0
    w0, h0 = sample.size
    for ext, path in samples:
        try:
            pixmap = gui.pil_to_qpixmap(OCREngine.read_image(path))
            # ico 格式规范上限 256×256，小图会被降采样，属正常现象
            expect_same = ext != ".ico"
            good = (not pixmap.isNull()) and (
                (pixmap.width() == w0 and pixmap.height() == h0) if expect_same
                else pixmap.width() > 0)
            ok_gui += good
            flag = "通过" if good else "失败"
            note = "" if expect_same else "（ICO 规范上限 256，已降采样）"
            print(f"  [{flag}] {ext:<6} {pixmap.width()}×{pixmap.height()}{note}")
        except Exception as e:                        # noqa: BLE001
            print(f"  [失败] {ext:<6} {type(e).__name__}: {e}")

    # ---- 扩展名判定（大小写不敏感）----
    print("\n[3] 扩展名判定")
    cases = [("a.PNG", True), ("b.JpG", True), ("c.webp", True),
             ("d.txt", False), ("e.pdf", False), ("f", False)]
    ok_ext = 0
    for name, want in cases:
        got = is_supported_ext(name)
        good = got == want
        ok_ext += good
        print(f"  [{'通过' if good else '失败'}] {name:<8} -> {got}（预期 {want}）")

    total = len(samples) * 2 + len(cases)
    passed = ok_ocr + ok_gui + ok_ext
    print("\n" + "=" * 60)
    print(f"识别 {ok_ocr}/{len(samples)}｜载入 {ok_gui}/{len(samples)}｜"
          f"判定 {ok_ext}/{len(cases)}")
    print(f"===== 结果：{passed}/{total} 项通过 =====")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
