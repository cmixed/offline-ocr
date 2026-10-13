# -*- coding: utf-8 -*-
"""
OCR 小软件 —— OCR 模型预下载脚本

把识别所需的模型提前下载到本地缓存，好处：
- 打包 / 部署后首次运行无需联网下载，开箱即用
- 离线环境也能正常识别

模型缓存目录：默认 ~/.paddlex/official_models（运行时会打印实际路径）

用法：
    .venv\\Scripts\\python.exe src\\download_models.py
"""
import os
import sys
import time

# 保证能 import 同目录的 ocr_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr_engine import OCREngine


def main() -> int:
    line = "=" * 56
    print(line)
    print("  OCR 模型预下载")
    print(line)

    engine = OCREngine()
    print(f"  文本检测模型：{engine.det_model}")
    print(f"  文本识别模型：{engine.rec_model}")
    print(f"  缓存目录：{OCREngine.models_dir()}")
    print()
    print("正在下载并加载模型（首次约需 1~2 分钟，请耐心等待）...")

    start = time.time()
    try:
        engine.preload()
    except Exception as e:                       # noqa: BLE001
        print()
        print(f"[失败] 模型下载失败：{e}")
        print("可能原因：网络不通，或无法访问模型源。")
        print("提示：不预下载也不影响使用 —— 首次识别时会自动重试下载。")
        return 1

    elapsed = time.time() - start
    print()
    print(f"[完成] 模型已就绪，用时 {elapsed:.1f} 秒")
    print(f"       缓存位置：{OCREngine.models_dir()}")
    print("       之后启动程序可离线识别（非首次打开无需等待下载）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
