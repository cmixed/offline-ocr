# -*- coding: utf-8 -*-
"""
OCR 小软件 —— OCR 引擎封装

把 PaddleOCR 的调用逻辑封装成可复用的 OCREngine 类，
供命令行脚本、GUI 界面、模型预下载脚本共用。

设计要点：
- 懒加载：引擎只在第一次识别时初始化，加快程序启动
- 中文路径安全：统一「PIL 读图 -> ndarray」再送入识别，避免路径含中文时失败
- 超大图自动压缩：最长边超过 MAX_SIDE 先等比缩小，识别后把框坐标还原回原图
- 结果结构化：返回 OCRLine 列表，便于界面展示和导出
- 标注图生成：内置 draw_annotated()，供 GUI 显示检测框
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

# 超大图阈值：最长边超过该值时，先等比压缩再识别。
# 像素过大既显著拖慢识别速度，对精度的增益也很有限。
MAX_SIDE = 4000

# 支持的图片扩展名（唯一的「格式真相来源」，GUI 与脚本共用）。
# 判定依据是 PIL 能否解码 —— 因为所有图片统一走 PIL 读入，
# 不依赖 Qt / OpenCV 各自的格式支持列表，二者不会出现「能显示但识别不了」的错位。
SUPPORTED_EXTS = (
    ".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".webp",
    ".tif", ".tiff", ".gif", ".ico", ".tga",
    ".ppm", ".pgm", ".pbm", ".pnm", ".xbm", ".xpm",
)


def is_supported_ext(path: str) -> bool:
    """扩展名是否在支持列表内（仅用于给出友好提示，不作解码依据）"""
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def file_dialog_filter() -> str:
    """文件选择对话框的过滤器字符串（由 SUPPORTED_EXTS 生成，避免两处不一致）"""
    patterns = " ".join(f"*{e}" for e in SUPPORTED_EXTS)
    return f"图片文件 ({patterns});;所有文件 (*)"


@dataclass
class OCRLine:
    """一行识别结果"""
    text: str
    score: float
    box: Optional[List[List[float]]] = field(default=None)


class OCREngine:
    """PaddleOCR 引擎封装（单例式使用，模型只加载一次）"""

    def __init__(
        self,
        det_model: str = "PP-OCRv5_mobile_det",
        rec_model: str = "PP-OCRv5_mobile_rec",
    ):
        self._det_model = det_model
        self._rec_model = rec_model
        self._ocr = None

    # ---------- 模型加载 ----------

    def preload(self) -> None:
        """预先加载模型（首次调用会触发下载）。

        供 setup / 模型预下载脚本调用，让首次识别不必再等待模型下载。
        """
        self._ensure_loaded()

    def _ensure_loaded(self):
        """懒加载模型（首次调用会下载模型，可能耗时较久）"""
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(
                text_detection_model_name=self._det_model,
                text_recognition_model_name=self._rec_model,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载到内存"""
        return self._ocr is not None

    @property
    def det_model(self) -> str:
        """当前使用的文本检测模型名"""
        return self._det_model

    @property
    def rec_model(self) -> str:
        """当前使用的文本识别模型名"""
        return self._rec_model

    @staticmethod
    def models_dir() -> str:
        """PaddleX 官方模型缓存目录（首次运行会自动下载到此处）"""
        return os.path.join(os.path.expanduser("~"), ".paddlex", "official_models")

    # ---------- 识别 ----------

    def recognize(self, image_path: str) -> List[OCRLine]:
        """识别单张图片，返回 OCRLine 列表。

        返回的 box 坐标已还原到「原图坐标系」，
        因此即使内部做了超大图压缩，也能直接画在原图上。
        """
        if not image_path or not os.path.exists(image_path):
            raise FileNotFoundError(f"图片不存在：{image_path}")
        if not os.path.isfile(image_path):
            raise ValueError(f"不是有效的文件：{image_path}")

        img = self.read_image(image_path)
        orig_w, orig_h = img.size

        # 超大图先等比压缩，ratio 用于把识别框坐标还原回原图
        ratio = 1.0
        longest = max(orig_w, orig_h)
        if longest > MAX_SIDE:
            ratio = longest / float(MAX_SIDE)
            new_size = (max(1, int(orig_w / ratio)), max(1, int(orig_h / ratio)))
            img = img.resize(new_size, Image.LANCZOS)

        self._ensure_loaded()
        result = self._ocr.predict(input=self._to_bgr(img))

        lines: List[OCRLine] = []
        for res in result:
            rec_texts = res.get("rec_texts", [])
            rec_scores = res.get("rec_scores", [])
            rec_polys = res.get("rec_polys", None)
            if rec_polys is None:
                rec_polys = res.get("dt_polys", [])

            for i, text in enumerate(rec_texts):
                box = None
                if i < len(rec_polys):
                    box = [[float(p[0]) * ratio, float(p[1]) * ratio]
                           for p in rec_polys[i]]
                score = float(rec_scores[i]) if i < len(rec_scores) else 0.0
                lines.append(OCRLine(text=text, score=score, box=box))

        return lines

    # ---------- 静态工具方法 ----------

    @staticmethod
    def read_image(path: str) -> Image.Image:
        """读图为 RGB 的 PIL Image（公开方法，GUI 载入图片时也走这里）。

        统一走 PIL 而不是把路径直接交给 PaddleOCR 或 Qt：
        - 兼容含中文 / 空格的路径
        - 立刻触发解码，损坏文件在此暴露为可读异常
        - 保证「能显示的图」与「能识别的图」完全一致
        """
        try:
            with Image.open(path) as im:
                im.load()
                return im.convert("RGB")
        except UnidentifiedImageError:
            exts = " / ".join(e.lstrip(".") for e in SUPPORTED_EXTS)
            raise ValueError(
                f"无法识别的图片格式（文件可能已损坏，或不是图片）：\n{path}\n\n"
                f"支持的格式：{exts}")

    @staticmethod
    def _to_bgr(img: Image.Image) -> np.ndarray:
        """RGB 的 PIL Image -> BGR 的 ndarray（OpenCV / PaddleOCR 约定）"""
        arr = np.asarray(img, dtype=np.uint8)
        return np.ascontiguousarray(arr[:, :, ::-1])

    @staticmethod
    def to_text(lines: List[OCRLine]) -> str:
        """把识别结果拼成纯文本（每行一条）"""
        return "\n".join(line.text for line in lines)

    @staticmethod
    def load_font(size: int = 22):
        """加载中文字体（cv2 不支持中文，改用 PIL）"""
        for font_path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()

    @classmethod
    def draw_annotated(cls, image_path: str, lines: List[OCRLine]) -> Image.Image:
        """在原图上画出检测框和识别文字，返回 PIL Image。

        注意：box 必须是原图坐标系（recognize() 已保证）。
        """
        img = cls.read_image(image_path)
        draw = ImageDraw.Draw(img)
        font = cls.load_font(22)

        for line in lines:
            if not line.box:
                continue
            poly = [tuple(p) for p in line.box]
            draw.polygon(poly, outline=(0, 200, 0), width=3)
            x, y = poly[0]
            # 只标注文本本身，不显示置信度
            draw.text((x, y - 28), line.text, fill=(220, 0, 0), font=font)

        return img
