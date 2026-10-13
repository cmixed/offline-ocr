# -*- coding: utf-8 -*-
"""
OCR 小软件 —— GUI 主程序

功能：
- 拖拽图片 / 选择图片
- 一键识别（后台线程，界面不卡；带进度条 + 忙碌光标反馈）
- 原图 / 标注图一键切换
- 图片滚轮缩放、适应窗口、原始大小
- 复制结果到剪贴板（纯文本）
- 导出为 TXT / Markdown（纯文本）

说明：识别结果只输出图片中的文本本身，不包含置信度等附加信息。

用法：
    .venv/Scripts/python.exe src/main.py
"""
import os
import sys

# 保证能 import 同目录的 ocr_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QScrollArea, QCheckBox, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QFont, QIcon

from ocr_engine import (
    MAX_SIDE, OCREngine, OCRLine, SUPPORTED_EXTS,
    file_dialog_filter, is_supported_ext,
)

# 全局引擎（模型只加载一次）
engine = OCREngine()

PLACEHOLDER = "把图片拖到这里\n\n或点击「选择图片」"


def _asset_path(name: str) -> str:
    """定位 assets/ 下的资源文件（如 icon.ico）。

    兼容两种运行方式：
    - 源码运行：main.py 在 src/ 下，assets/ 在其上层目录
    - PyInstaller 打包后：资源被解包到临时目录 sys._MEIPASS
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def pil_to_qpixmap(pil_img) -> QPixmap:
    """PIL Image -> QPixmap"""
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                  QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


class ImageCanvas(QScrollArea):
    """图片显示区：支持滚轮缩放、适应窗口、原始大小。

    放在 QScrollArea 里，放大后可拖动滚动条查看细节。
    """

    ZOOM_MIN = 0.05
    ZOOM_MAX = 8.0
    ZOOM_STEP = 1.15

    zoomChanged = Signal(int)   # 当前显示比例（百分比）

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidgetResizable(False)
        self.setStyleSheet(
            "QScrollArea { border: 1px dashed #999; background: #fafafa; }"
        )

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        self._label.setText(PLACEHOLDER)
        self._label.resize(420, 300)
        # 让鼠标事件穿透到滚动区域，这样才能实现「按住鼠标拖动画面」
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWidget(self._label)

        self._source = None       # QPixmap
        self._zoom = 1.0          # 非适应模式下的缩放倍率
        self._fit_mode = True     # 适应窗口模式

        # 拖动平移（pan）状态
        self._panning = False
        self._pan_start = None
        self._pan_scroll = (0, 0)

    # ---------- 对外接口 ----------

    def set_image(self, pixmap: QPixmap, keep_view: bool = False):
        """设置显示的图片。keep_view=True 时保留当前缩放状态（用于原图/标注图切换）"""
        self._source = pixmap
        if not keep_view:
            self._fit_mode = True
            self._zoom = 1.0
        self._apply()

    def clear(self):
        """恢复占位提示"""
        self._source = None
        self._fit_mode = True
        self._zoom = 1.0
        self._label.setPixmap(QPixmap())
        self._label.setText(PLACEHOLDER)
        self._label.resize(max(420, self.viewport().width()),
                           max(300, self.viewport().height()))
        self.zoomChanged.emit(0)

    def fit_window(self):
        """适应窗口（只缩小不放大）"""
        if self._source is None:
            return
        self._fit_mode = True
        self._apply()

    def actual_size(self):
        """原始大小 1:1"""
        if self._source is None:
            return
        self._fit_mode = False
        self._zoom = 1.0
        self._apply()

    def zoom_by(self, factor: float):
        """按倍率缩放（滚轮调用）"""
        if self._source is None:
            return
        self._fit_mode = False
        self._zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        self._apply()

    # ---------- 内部实现 ----------

    def _apply(self):
        if self._source is None:
            return
        src_w, src_h = self._source.width(), self._source.height()
        if src_w == 0 or src_h == 0:
            return

        if self._fit_mode:
            vp = self.viewport().size()
            if src_w > vp.width() or src_h > vp.height():
                scaled = self._source.scaled(
                    vp, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
            else:
                scaled = self._source      # 小图不放大，保持清晰
        else:
            w = max(1, int(src_w * self._zoom))
            h = max(1, int(src_h * self._zoom))
            scaled = self._source.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)

        self._label.setText("")
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())
        self.zoomChanged.emit(int(round(scaled.width() / src_w * 100)))
        self._update_cursor()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode:
            self._apply()

    def wheelEvent(self, event):
        """滚轮缩放"""
        if self._source is None or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        self.zoom_by(self.ZOOM_STEP if delta > 0 else 1.0 / self.ZOOM_STEP)
        event.accept()

    # ---------- 拖动平移（放大后按住鼠标拖动画面） ----------

    def _can_pan(self) -> bool:
        """图片超出可视区域时才允许拖动"""
        if self._source is None:
            return False
        return (self._label.width() > self.viewport().width()
                or self._label.height() > self.viewport().height())

    def _update_cursor(self):
        """可拖动时显示手型光标，提示用户「这里能拖」"""
        if self._panning:
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._can_pan():
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._can_pan():
            self._panning = True
            self._pan_start = event.position().toPoint()
            self._pan_scroll = (self.horizontalScrollBar().value(),
                                self.verticalScrollBar().value())
            self._update_cursor()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self.horizontalScrollBar().setValue(self._pan_scroll[0] - delta.x())
            self.verticalScrollBar().setValue(self._pan_scroll[1] - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self._pan_start = None
            self._update_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- 拖入文件的视觉反馈 ----------

    def set_highlight(self, on: bool):
        """拖拽文件悬停时高亮边框，让用户明确「可以松手了」"""
        if on:
            self.setStyleSheet(
                "QScrollArea { border: 2px dashed #2a7; background: #eefaf3; }")
        else:
            self.setStyleSheet(
                "QScrollArea { border: 1px dashed #999; background: #fafafa; }")


class RecognizeWorker(QThread):
    """后台识别线程，避免界面卡死"""
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, image_path: str):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            lines = engine.recognize(self.image_path)
            self.done.emit(lines)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR 小软件")
        self.resize(1080, 680)
        self.setAcceptDrops(True)

        self.image_path = None
        self.lines: list[OCRLine] = []
        self.pixmap_orig = None
        self.pixmap_annot = None
        self.last_dir = ""

        self._build_ui()

    # ---------- 界面构建 ----------

    def _build_ui(self):
        # --- 顶部按钮栏 ---
        self.btn_open = QPushButton("选择图片")
        self.btn_run = QPushButton("开始识别")
        self.btn_copy = QPushButton("复制结果")
        self.btn_export = QPushButton("导出文件")
        self.btn_run.setEnabled(False)
        self.btn_copy.setEnabled(False)
        self.btn_export.setEnabled(False)

        self.btn_open.clicked.connect(self.on_open)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_copy.clicked.connect(self.on_copy)
        self.btn_export.clicked.connect(self.on_export)

        toolbar = QHBoxLayout()
        for b in (self.btn_open, self.btn_run, self.btn_copy, self.btn_export):
            toolbar.addWidget(b)
        toolbar.addStretch()

        # --- 左侧：图片工具条 + 画布 ---
        self.image_canvas = ImageCanvas()
        self.image_canvas.zoomChanged.connect(self.on_zoom_changed)

        self.chk_annot = QCheckBox("显示识别框")
        self.chk_annot.setEnabled(False)
        self.chk_annot.setToolTip("勾选显示识别框（标注图），取消则显示原图")
        self.chk_annot.toggled.connect(self.on_toggle_annot)

        self.btn_fit = QPushButton("适应窗口")
        self.btn_actual = QPushButton("原始大小")
        self.btn_fit.clicked.connect(self.image_canvas.fit_window)
        self.btn_actual.clicked.connect(self.image_canvas.actual_size)

        self.lbl_zoom = QLabel("—")
        self.lbl_zoom.setMinimumWidth(46)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_zoom.setStyleSheet("color: #888;")

        img_toolbar = QHBoxLayout()
        img_toolbar.addWidget(self.chk_annot)
        img_toolbar.addSpacing(8)
        img_toolbar.addWidget(self.btn_fit)
        img_toolbar.addWidget(self.btn_actual)
        img_toolbar.addStretch()
        img_toolbar.addWidget(self.lbl_zoom)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addLayout(img_toolbar)
        left_layout.addWidget(self.image_canvas)

        # --- 右侧：结果区 ---
        self.text_result = QTextEdit()
        self.text_result.setPlaceholderText("识别结果会显示在这里……")
        self.text_result.setStyleSheet("font-size: 15px;")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.text_result)
        splitter.setSizes([660, 400])

        # --- 总布局 ---
        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(splitter)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # --- 状态栏 + 进度条 ---
        self.setStatusBar(QStatusBar())
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)          # 0,0 = 不确定进度（忙碌态）
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(140)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("就绪")

        self._update_tool_state()

    def _update_tool_state(self):
        """图片工具条可用性"""
        has_src = self.pixmap_orig is not None
        self.btn_fit.setEnabled(has_src)
        self.btn_actual.setEnabled(has_src)
        self.chk_annot.setEnabled(self.pixmap_annot is not None)

    # ---------- 交互：识别流程 ----------

    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", self.last_dir, file_dialog_filter()
        )
        if path:
            self.load_image(path)

    def load_image(self, path: str):
        # 与识别共用同一套解码（PIL），保证「能显示的图」必定「能识别」
        try:
            pil_img = OCREngine.read_image(path)
        except (ValueError, FileNotFoundError, OSError, PermissionError) as e:
            QMessageBox.warning(self, "无法载入图片", str(e))
            return

        pixmap = pil_to_qpixmap(pil_img)
        self.image_path = path
        self.last_dir = os.path.dirname(path)
        self.pixmap_orig = pixmap
        self.pixmap_annot = None
        self.image_canvas.set_image(pixmap)

        # 重置标注开关（避免信号触发多余的刷新）
        self.chk_annot.blockSignals(True)
        self.chk_annot.setChecked(False)
        self.chk_annot.blockSignals(False)

        self.text_result.clear()
        self.lines = []
        self.btn_run.setEnabled(True)
        self.btn_copy.setEnabled(False)
        self.btn_export.setEnabled(False)
        self._update_tool_state()

        msg = f"已载入：{os.path.basename(path)}（{pixmap.width()}×{pixmap.height()}）"
        if max(pixmap.width(), pixmap.height()) > MAX_SIDE:
            msg += f"｜图片较大，识别时将自动压缩到 {MAX_SIDE}px 以内"
        self.statusBar().showMessage(msg)

    def on_run(self):
        if not self.image_path:
            return
        self._set_busy(True, "正在识别……（首次运行需加载模型，请稍候）")

        self.worker = RecognizeWorker(self.image_path)
        self.worker.done.connect(self.on_recognized)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_recognized(self, lines: list):
        self._set_busy(False)
        self.lines = lines
        self.btn_run.setEnabled(True)

        if not lines:
            self.text_result.setPlainText("（未识别到文字）")
            self.statusBar().showMessage("未识别到文字，可换更清晰的图片试试")
            return

        # 结果区：只输出识别到的文本（纯文本，不带置信度）
        self.text_result.setPlainText(OCREngine.to_text(lines))
        self.btn_copy.setEnabled(True)
        self.btn_export.setEnabled(True)

        # 生成标注图并默认显示；失败时降级为「只给文字」，不影响主流程
        note = ""
        try:
            annotated = OCREngine.draw_annotated(self.image_path, lines)
            self.pixmap_annot = pil_to_qpixmap(annotated)
            self.chk_annot.setEnabled(True)
            self.chk_annot.setChecked(True)      # 触发 on_toggle_annot
            self._show_current_pixmap()
        except Exception:                        # noqa: BLE001
            self.pixmap_annot = None
            self.chk_annot.blockSignals(True)
            self.chk_annot.setChecked(False)
            self.chk_annot.blockSignals(False)
            self.chk_annot.setEnabled(False)
            note = "｜标注图生成失败，仅显示文字"

        self.statusBar().showMessage(
            f"识别完成，共 {len(lines)} 行（可滚轮缩放查看细节）{note}")

    def on_failed(self, msg: str):
        self._set_busy(False)
        self.btn_run.setEnabled(True)
        self.statusBar().showMessage("识别失败")
        QMessageBox.critical(self, "识别失败", msg)

    def _set_busy(self, busy: bool, msg: str = ""):
        """统一管理识别中的界面反馈：按钮文字、进度条、忙碌光标"""
        if busy:
            self.btn_run.setEnabled(False)
            self.btn_run.setText("识别中…")
            self.progress.show()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(msg)
        else:
            self.btn_run.setEnabled(bool(self.image_path))
            self.btn_run.setText("开始识别")
            self.progress.hide()
            QApplication.restoreOverrideCursor()

    # ---------- 交互：图片显示 ----------

    def on_toggle_annot(self, checked: bool):
        """原图 / 标注图切换"""
        self._show_current_pixmap()

    def _show_current_pixmap(self):
        if self.chk_annot.isChecked() and self.pixmap_annot is not None:
            pm = self.pixmap_annot
        else:
            pm = self.pixmap_orig
        if pm is not None:
            # keep_view=True：切换时保留缩放状态，方便对比同一处细节
            self.image_canvas.set_image(pm, keep_view=True)

    def on_zoom_changed(self, percent: int):
        self.lbl_zoom.setText(f"{percent}%" if percent else "—")

    # ---------- 交互：结果落地 ----------

    def on_copy(self):
        if not self.lines:
            return
        text = OCREngine.to_text(self.lines)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("已复制到剪贴板")

    def on_export(self):
        if not self.lines:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", os.path.join(self.last_dir, "ocr_result.txt"),
            "文本文件 (*.txt);;Markdown 文件 (*.md)"
        )
        if not path:
            return
        text = OCREngine.to_text(self.lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.statusBar().showMessage(f"已导出：{os.path.basename(path)}")

    # ---------- 拖拽支持 ----------

    def dragEnterEvent(self, event):
        """从文件夹把图片拖进窗口"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.image_canvas.set_highlight(True)

    def dragLeaveEvent(self, event):
        self.image_canvas.set_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.image_canvas.set_highlight(False)
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if not paths:
            return

        # 只挑出扩展名在支持列表内的文件，避免把文件夹 / 文档拖进来后报一堆错
        supported = [p for p in paths if is_supported_ext(p)]
        if not supported:
            exts = " / ".join(e.lstrip(".") for e in SUPPORTED_EXTS)
            QMessageBox.warning(
                self, "不支持的格式",
                "拖入的文件里没有可识别的图片。\n\n"
                f"支持的格式：{exts}\n\n"
                "也可以用「选择图片」→ 选择「所有文件」强制尝试载入。")
            return

        self.load_image(supported[0])
        if len(paths) > 1:
            self.statusBar().showMessage(
                f"{self.statusBar().currentMessage()}"
                f"｜本次拖入 {len(paths)} 个文件，暂不支持批量")


def main():
    app = QApplication(sys.argv)
    # 显式指定中文字体，保证跨环境中文显示正常
    app.setFont(QFont("Microsoft YaHei", 10))

    # 应用图标：影响窗口标题栏、任务栏与 Alt+Tab 切换
    icon_file = _asset_path("icon.ico")
    if os.path.exists(icon_file):
        app.setWindowIcon(QIcon(icon_file))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
