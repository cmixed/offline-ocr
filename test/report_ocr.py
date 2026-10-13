# -*- coding: utf-8 -*-
"""
OCR 小软件 —— HTML 可视化报告生成器

用途：生成一个自包含的 HTML 报告页，包含：
      - 原图
      - 标注结果图（检测框 + 文字）
      - 识别文本列表
      - 结构化 JSON 数据

图片以 base64 嵌入，单文件可直接分享。

用法：
    .venv/Scripts/python.exe test/report_ocr.py <图片路径> [输出html路径]

示例：
    .venv/Scripts/python.exe test/report_ocr.py test_image.png
    （默认输出 ocr_report.html）
"""
import sys
import os
import json
import base64
import io
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont


def load_font(size=24):
    for font_path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def img_to_base64(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_report(image_path: str, output_html: str = "ocr_report.html"):
    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    result = ocr.predict(input=image_path)

    orig_img = Image.open(image_path).convert("RGB")
    vis_img = orig_img.copy()
    draw = ImageDraw.Draw(vis_img)
    font = load_font(24)

    texts, items = [], []
    for res in result:
        rec_texts = res.get("rec_texts", [])
        rec_polys = res.get("rec_polys", None)
        if rec_polys is None:
            rec_polys = res.get("dt_polys", [])

        for i, text in enumerate(rec_texts):
            poly = None
            if i < len(rec_polys):
                poly = [tuple(map(float, p)) for p in rec_polys[i]]
                draw.polygon(poly, outline=(0, 200, 0), width=3)
                x, y = poly[0]
                draw.text((x, y - 30), text, fill=(220, 0, 0), font=font)
            texts.append(text)
            items.append({
                "text": text,
                "box": [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in poly] if poly else None,
            })

    orig_b64 = img_to_base64(orig_img)
    vis_b64 = img_to_base64(vis_img)

    rows = "\n".join(
        f'<tr><td>{i+1}</td><td class="txt">{t}</td></tr>'
        for i, t in enumerate(texts)
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>OCR 识别报告 - {os.path.basename(image_path)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft YaHei", sans-serif; background: #f5f6f8; margin: 0; padding: 24px; color: #222; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .card h2 {{ font-size: 15px; margin: 0 0 12px; color: #444; font-weight: 500; }}
  .card img {{ width: 100%; border-radius: 6px; display: block; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  th, td {{ padding: 10px 14px; text-align: left; font-size: 14px; border-bottom: 1px solid #eee; }}
  th {{ background: #fafafa; color: #666; font-weight: 500; }}
  td.txt {{ font-size: 15px; }}
  pre {{ background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 10px; overflow-x: auto; font-size: 13px; }}
  .stat {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-bottom: 16px; }}
</style>
</head>
<body>
  <h1>OCR 识别报告</h1>
  <div class="meta">图片：{os.path.basename(image_path)}</div>
  <div class="stat">共识别 {len(texts)} 处文字</div>

  <div class="grid">
    <div class="card"><h2>原图</h2><img src="data:image/png;base64,{orig_b64}" alt="原图"></div>
    <div class="card"><h2>识别标注（绿框=位置，红字=结果）</h2><img src="data:image/png;base64,{vis_b64}" alt="标注图"></div>
  </div>

  <div class="card" style="margin-bottom:24px;">
    <h2>识别文本</h2>
    <table>
      <thead><tr><th style="width:60px">#</th><th>识别文本</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>结构化数据（JSON）</h2>
    <pre>{json.dumps(items, ensure_ascii=False, indent=2)}</pre>
  </div>
</body>
</html>"""

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"共识别 {len(texts)} 处文字")
    print(f"报告已生成：{os.path.abspath(output_html)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：.venv/Scripts/python.exe test/report_ocr.py <图片路径> [输出html路径]")
        sys.exit(1)

    img_path = sys.argv[1]
    out_html = sys.argv[2] if len(sys.argv) > 2 else "ocr_report.html"
    build_report(img_path, out_html)
