# -*- coding: utf-8 -*-
"""
OCR 小软件 —— GUI 主程序

三个功能模块（见 MODES 注册表，新增模块只需往表里加一项）：
- 普通识别：拖拽 / 选择图片，识别全部文字
- 即时识别：框选屏幕区域（Ctrl+Shift+A），松手立即识别
- 表格识别：识别表格结构，预览并导出 Excel

通用能力：
- 后台线程识别（界面不卡；进度条 + 忙碌光标反馈）
- 原图 / 标注图一键切换、滚轮缩放、适应窗口、原始大小
- 复制结果（文本 / 制表符表格）、导出 TXT / Markdown / XLSX
- 快捷键可自定义（设置面板，QSettings 持久化）
- 记住窗口大小、上次目录与上次模式

说明：文字识别结果只输出图片中的文本本身，不包含置信度等附加信息。

用法：
    .venv/Scripts/python.exe src/main.py
    .venv/Scripts/python.exe src/main.py --selftest
"""
import io
import os
import shutil
import sys

# 保证能 import 同目录的 ocr_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QScrollArea, QCheckBox, QProgressBar, QDialog, QDialogButtonBox,
    QGroupBox, QGridLayout, QKeySequenceEdit, QComboBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QSettings, QBuffer, QIODevice, QDateTime, QRect,
    QTimer,
)
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QIcon, QKeySequence, QShortcut, QGuiApplication,
    QCursor, QPainter, QColor, QPen,
)

from ocr_engine import (
    MAX_SIDE, OCREngine, OCRLine, SUPPORTED_EXTS, TableEngine, TableResult,
    file_dialog_filter, is_supported_ext,
)

# 全局引擎（模型只加载一次）
engine = OCREngine()
table_engine = TableEngine()

PLACEHOLDER = "把图片拖到这里\n\n或点击「选择图片」"

# ---------- 快捷键定义与持久化 ----------
#
# DEFAULT_SHORTCUTS 是唯一来源：默认值、绑定、设置面板、测试都读它。
# 结构：(动作键, 说明, 默认按键元组)
# 一个动作可以有多个按键（例如 Ctrl+Enter 同时覆盖主键盘与小键盘回车）。
DEFAULT_SHORTCUTS = [
    ("open", "选择图片", ("Ctrl+O",)),
    ("capture", "截取屏幕（即时识别）", ("Ctrl+Shift+A",)),
    ("run", "开始识别 / 识别表格", ("Ctrl+Enter", "Ctrl+Return")),
    ("copy", "复制识别结果（Ctrl+C 留给结果框自己）", ("Ctrl+Shift+C",)),
    ("export", "导出为 TXT / Markdown / Excel", ("Ctrl+S",)),
    ("fit", "适应窗口", ("Ctrl+0",)),
    ("actual", "原始大小（1:1）", ("Ctrl+1",)),
    ("annot", "切换原图 / 识别框图", ("Ctrl+B",)),
    ("settings", "打开设置面板", ("F1",)),
]

# 用户改过的按键存在这里（Windows 下即注册表 HKCU\Software\QIWANYANG\ocrapp）
SETTINGS_ORG = "QIWANYANG"
SETTINGS_APP = "ocrapp"


def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def load_shortcuts(settings: QSettings | None = None) -> dict:
    """读取用户的快捷键配置，返回 {动作键: (按键序列, ...)}。

    未配置过的动作回落到默认值；用户主动清空的动作保存为空元组（= 不绑定）。
    为此用 None 作默认值来区分「没存过」与「存了空字符串」。
    """
    s = settings or _settings()
    result = {}
    for name, _desc, defaults in DEFAULT_SHORTCUTS:
        raw = s.value(f"shortcuts/{name}", None)
        if raw is None:
            result[name] = tuple(defaults)
            continue
        # 序列内不含分号，用分号连接多个按键
        parts = tuple(p.strip() for p in str(raw).split(";") if p.strip())
        # 过滤掉无法解析的脏数据（例如手工改过配置）
        result[name] = tuple(p for p in parts if not QKeySequence(p).isEmpty())
    return result


def save_shortcuts(mapping: dict, settings: QSettings | None = None) -> None:
    """把快捷键配置写入 QSettings。"""
    s = settings or _settings()
    for name, _desc, _defaults in DEFAULT_SHORTCUTS:
        seqs = mapping.get(name, ())
        s.setValue(f"shortcuts/{name}", ";".join(seqs))
    s.sync()


def shortcuts_to_text(seqs) -> str:
    """给界面用：把按键序列拼成 "Ctrl+Enter / Ctrl+Return" 这种可读形式。"""
    return " / ".join(seqs) if seqs else ""


# ---------- 功能模块（模式）注册表 ----------
#
# 想加新模块（例如「批量识别」「票据识别」）时，只需：
#   1. 在这里追加一项
#   2. 在 MainWindow 里实现 on_pick / on_run 指定的方法
#   3. 若结果形态不是纯文本，在 _build_result_area() 里加一个结果页
# 主界面会按注册表自动生成入口，不需要改工具栏布局。
MODES = [
    {
        "key": "basic",
        "name": "普通识别",
        "hint": "选择或拖入图片，识别全部文字",
        "pick": "选择图片",
        "run": "开始识别",
        "result": "text",
        "on_pick": "on_pick_file",
        "on_run": "on_run_ocr",
    },
    {
        "key": "instant",
        "name": "即时识别",
        "hint": "点「截取屏幕」框选区域，松手立即识别（Ctrl+Shift+A）",
        "pick": "截取屏幕",
        "run": None,                 # 截完自动识别，不需要再点一次
        "result": "text",
        "on_pick": "on_capture_screen",
        "on_run": None,
    },
    {
        "key": "table",
        "name": "表格识别",
        "hint": "选择表格图片，识别后可在右侧预览并导出 Excel",
        "pick": "选择图片",
        "run": "识别表格",
        "result": "table",
        "on_pick": "on_pick_file",
        "on_run": "on_run_table",
    },
]
MODE_BY_KEY = {m["key"]: m for m in MODES}


# ---------- 界面偏好（窗口大小 / 上次目录 / 上次模式） ----------

def load_ui_prefs(settings: QSettings | None = None) -> dict:
    s = settings or _settings()
    return {
        "remember": s.value("ui/remember", True, type=bool),
        "mode": s.value("ui/mode", "basic", type=str),
        "last_dir": s.value("ui/last_dir", "", type=str),
    }


def save_ui_prefs(remember: bool, settings: QSettings | None = None) -> None:
    s = settings or _settings()
    s.setValue("ui/remember", bool(remember))
    if not remember:
        # 关掉记忆时顺手清掉已存的窗口状态，避免下次打开又「诈尸」
        for key in ("ui/geometry", "ui/splitter", "ui/last_dir", "ui/mode"):
            s.remove(key)
    s.sync()


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


def _ensure_bundled_models() -> None:
    """把打包内置的 OCR 模型复制到用户缓存目录（仅打包运行时生效）。

    模型随包分发是为了「开箱即用、完全离线」；但仍复制到 paddlex 惯用的
    ~/.paddlex/official_models/ 路径，因为该目录可写 —— paddlex 需要在其下
    创建 locks / temp / func_ret 等子目录，而打包解包目录未必可写。

    已存在同名模型则跳过，不覆盖用户可能自行更新的版本。
    """
    if not getattr(sys, "frozen", False):
        return
    src_root = os.path.join(
        getattr(sys, "_MEIPASS", ""), "paddlex_models", "official_models")
    if not os.path.isdir(src_root):
        return
    # 与 paddlex 的缓存定位保持一致：优先读环境变量，否则用 ~/.paddlex
    cache_home = os.environ.get("PADDLE_PDX_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".paddlex")
    dst_root = os.path.join(cache_home, "official_models")
    for name in os.listdir(src_root):
        src = os.path.join(src_root, name)
        dst = os.path.join(dst_root, name)
        if not os.path.isdir(src) or os.path.isdir(dst):
            continue
        try:
            os.makedirs(dst_root, exist_ok=True)
            shutil.copytree(src, dst)
        except OSError:
            # 复制失败不阻断启动：首次识别时会自行联网下载模型
            pass


def pil_to_qpixmap(pil_img) -> QPixmap:
    """PIL Image -> QPixmap"""
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                  QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def qpixmap_to_pil(pixmap: QPixmap) -> Image.Image:
    """QPixmap -> PIL Image（截图后直接进识别，不必先写临时文件）"""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


class ScreenCaptureOverlay(QWidget):
    """全屏框选遮罩：截取光标所在屏幕，拖出矩形后返回该区域。

    设计取舍：
    - 只截「光标所在屏幕」，而不是把所有屏幕拼成一张虚拟大图。
      多屏时把鼠标移到目标屏幕再按快捷键即可，避免处理跨屏 DPI 不一致的坑。
    - 用自绘遮罩而不是 QRuband：需要「选区保持原亮度、其余压暗」的效果。
    """

    captured = Signal(QPixmap)
    cancelled = Signal()
    MIN_SIZE = 8          # 小于这个尺寸视为误点，不算一次框选

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._screen = (QGuiApplication.screenAt(QCursor.pos())
                        or QGuiApplication.primaryScreen())
        self._shot = self._screen.grabWindow(0)
        self._start = None
        self._end = None
        self.setGeometry(self._screen.geometry())

    # ---------- 坐标换算 ----------

    @staticmethod
    def map_rect(widget_size, pixmap_size, rect: QRect) -> QRect:
        """控件坐标 -> 原始截图像素坐标（处理高 DPI 缩放）。"""
        ww = max(1, widget_size[0])
        wh = max(1, widget_size[1])
        sx = pixmap_size[0] / ww
        sy = pixmap_size[1] / wh
        return QRect(round(rect.x() * sx), round(rect.y() * sy),
                     max(1, round(rect.width() * sx)),
                     max(1, round(rect.height() * sy)))

    def _selection(self) -> QRect:
        if self._start is None or self._end is None:
            return QRect()
        return QRect(self._start, self._end).normalized()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))

        sel = self._selection()
        if sel.width() > 0 and sel.height() > 0:
            # 选区还原为原亮度，让用户看清要识别的内容
            p.drawPixmap(sel, self._shot, self.map_rect(
                (self.width(), self.height()),
                (self._shot.width(), self._shot.height()), sel))
            p.setPen(QPen(QColor("#22a06b"), 2))
            p.drawRect(sel)
            p.setPen(QColor(255, 255, 255))
            p.drawText(sel.adjusted(6, 6, 0, 0),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       f"{sel.width()} × {sel.height()}")

        if self._start is None:
            p.setPen(QColor(255, 255, 255, 230))
            font = p.font()
            font.setPointSize(13)
            p.setFont(font)
            p.drawText(self.rect().adjusted(0, 48, 0, 0),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       "拖拽框选要识别的区域，按 Esc 或右键取消")

    # ---------- 交互 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._end = event.position().toPoint()
        sel = self._selection()
        self._start = self._end = None
        if sel.width() < self.MIN_SIZE or sel.height() < self.MIN_SIZE:
            self._cancel()
            return
        crop = self._shot.copy(self.map_rect(
            (self.width(), self.height()),
            (self._shot.width(), self._shot.height()), sel))
        self.captured.emit(crop)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _cancel(self):
        self.cancelled.emit()
        self.close()



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
    """后台识别线程，避免界面卡死（普通 / 即时模式）"""
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, image):
        super().__init__()
        self.image = image

    def run(self):
        try:
            self.done.emit(engine.recognize_image(self.image))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class TableWorker(QThread):
    """后台表格识别线程（表格模式）"""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, image):
        super().__init__()
        self.image = image

    def run(self):
        try:
            self.done.emit(table_engine.recognize(self.image))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SettingsDialog(QDialog):
    """设置面板：查看并重新绑定快捷键，保存后立即生效。

    三个约束保证「看到的就是生效的」：
    - 行内容来自 load_shortcuts()（用户配置），而不是另一份硬编码
    - 保存前做冲突检查，同一个组合键不能绑给两个动作
    - 保存成功后发 saved 信号，主窗口立刻重建 QShortcut，无需重启
    """

    saved = Signal(dict)

    EDIT_STYLE = (
        "QKeySequenceEdit { border: 1px solid #c9ced6; border-radius: 5px;"
        " padding: 3px 8px; background: white; color: #222;"
        " font-family: Consolas, 'Courier New', monospace; font-size: 12px; }"
        "QKeySequenceEdit:focus { border: 1px solid #2a7; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(600)
        self.setModal(True)

        self._edits: dict[str, QKeySequenceEdit] = {}
        current = load_shortcuts()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        group = QGroupBox("快捷键（点进输入框，直接按下新的组合键）")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)

        for row, (name, desc, _defaults) in enumerate(DEFAULT_SHORTCUTS):
            edit = QKeySequenceEdit()
            edit.setMaximumSequenceLength(4)          # 一个功能可填多个组合键（任一触发）
            edit.setStyleSheet(self.EDIT_STYLE)
            edit.setMinimumWidth(230)
            edit.setToolTip("直接按下新的组合键即可；右侧「清除」可解除绑定")
            edit.setKeySequence(QKeySequence(", ".join(current.get(name, ()))))
            self._edits[name] = edit

            clear_btn = QPushButton("清除")
            clear_btn.setFixedWidth(52)
            clear_btn.setToolTip("解除这个功能的快捷键绑定")
            clear_btn.clicked.connect(edit.clear)

            grid.addWidget(QLabel(desc), row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(clear_btn, row, 2)

        layout.addWidget(group)

        # --- 界面 ---
        ui_group = QGroupBox("界面")
        ui_layout = QVBoxLayout(ui_group)
        prefs = load_ui_prefs()
        self.chk_remember = QCheckBox("记住窗口大小、上次打开的目录和上次使用的模式")
        self.chk_remember.setChecked(prefs["remember"])
        ui_layout.addWidget(self.chk_remember)
        layout.addWidget(ui_group)

        hint = QLabel(
            "快捷键在整个窗口内生效；未载入图片或还没有识别结果时不会触发（与按钮可用状态一致）。\n"
            "一个功能可以填多个组合键（如 Ctrl+Enter, Ctrl+Return），按其中任意一个都生效。\n"
            "保存后立即生效，配置保存在本机，下次启动仍然有效。"
        )
        hint.setStyleSheet("color: #777;")
        layout.addWidget(hint)

        self.btn_default = QPushButton("恢复默认")
        self.btn_default.clicked.connect(self._restore_defaults)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(self.btn_default)
        bottom.addStretch()
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

    # ---------- 内部 ----------

    def _restore_defaults(self):
        for name, _desc, defaults in DEFAULT_SHORTCUTS:
            self._edits[name].setKeySequence(QKeySequence(", ".join(defaults)))

    def collect(self) -> dict:
        """把界面上的输入整理成 {动作键: (按键序列, ...)}。"""
        result = {}
        for name, edit in self._edits.items():
            ks = edit.keySequence()
            seqs = []
            for i in range(ks.count()):
                # ks[i] 是 QKeyCombination，需包回 QKeySequence 才能取文本
                text = QKeySequence(ks[i]).toString(
                    QKeySequence.SequenceFormat.PortableText)
                if text:
                    seqs.append(text)
            result[name] = tuple(seqs)
        return result

    @staticmethod
    def find_conflicts(mapping: dict) -> list:
        """返回冲突描述列表：同一个组合键绑给了多个动作。"""
        owners: dict[str, list] = {}
        for name, seqs in mapping.items():
            for seq in seqs:
                owners.setdefault(seq, [])
                if name not in owners[seq]:
                    owners[seq].append(name)
        desc = {name: desc for name, desc, _d in DEFAULT_SHORTCUTS}
        return [
            f"{seq} 同时绑给了：{'、'.join(desc[n] for n in names)}"
            for seq, names in owners.items() if len(names) > 1
        ]

    @staticmethod
    def find_invalid(mapping: dict) -> list:
        """挑出「无修饰键的普通键」——绑成快捷键会抢走输入，必须拒绝。

        例如把复制绑成 S：在结果框里打 s 就会触发复制，完全没法用。
        放行 F1~F35 这类功能键，它们不参与文字输入。
        """
        desc = {name: desc for name, desc, _d in DEFAULT_SHORTCUTS}
        bad = []
        for name, seqs in mapping.items():
            for seq in seqs:
                comb = QKeySequence(seq)[0]
                if comb.keyboardModifiers() != Qt.KeyboardModifier.NoModifier:
                    continue
                key = comb.key()
                if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35:
                    continue
                bad.append(f"{seq}（{desc[name]}）")
        return bad

    def _on_save(self):
        mapping = self.collect()
        conflicts = self.find_conflicts(mapping)
        if conflicts:
            QMessageBox.warning(
                self, "快捷键冲突",
                "同一个组合键不能同时绑定到两个功能：\n\n"
                + "\n".join(f"· {c}" for c in conflicts)
                + "\n\n请调整后再保存。")
            return
        invalid = self.find_invalid(mapping)
        if invalid:
            QMessageBox.warning(
                self, "快捷键不可用",
                "下面这些按键没有带 Ctrl / Alt / Shift，\n"
                "绑成快捷键后会在输入文字时误触发：\n\n"
                + "\n".join(f"· {x}" for x in invalid)
                + "\n\n请加上修饰键（如 Ctrl+S），或改用 F1~F12 功能键。")
            return
        save_shortcuts(mapping)
        save_ui_prefs(self.chk_remember.isChecked())
        self.saved.emit(mapping)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR 小软件")
        self.resize(1080, 680)
        self.setAcceptDrops(True)

        # 当前模式的图像是唯一来源：来自文件时 image_path 有值，截图时为空
        self.mode = "basic"
        self.image = None          # PIL.Image
        self.image_path = None
        self.image_name = ""
        self.lines: list[OCRLine] = []
        self.table: TableResult | None = None
        self.pixmap_orig = None
        self.pixmap_annot = None
        self.last_dir = ""

        self._busy = False
        self._cursor_overridden = False
        self._overlay = None
        self.worker = None

        self._build_ui()
        self._restore_ui_state()

    # ---------- 界面构建 ----------

    def _build_ui(self):
        # --- 模式选择（内容由 MODES 注册表生成，加模块不用改这里）---
        self.combo_mode = QComboBox()
        for mode in MODES:
            self.combo_mode.addItem(mode["name"], mode["key"])
        self.combo_mode.setMinimumWidth(110)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        # --- 顶部按钮栏 ---
        self.btn_pick = QPushButton("选择图片")
        self.btn_run = QPushButton("开始识别")
        self.btn_copy = QPushButton("复制结果")
        self.btn_export = QPushButton("导出文件")

        self.btn_pick.clicked.connect(self.on_pick)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_copy.clicked.connect(self.on_copy)
        self.btn_export.clicked.connect(self.on_export)

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setToolTip("查看与自定义快捷键")
        self.btn_settings.clicked.connect(self.open_settings)

        toolbar = QHBoxLayout()
        mode_label = QLabel("模式")
        mode_label.setStyleSheet("color: #666;")
        toolbar.addWidget(mode_label)
        toolbar.addWidget(self.combo_mode)
        toolbar.addSpacing(10)
        for b in (self.btn_pick, self.btn_run, self.btn_copy, self.btn_export):
            toolbar.addWidget(b)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_settings)

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

        # --- 右侧：结果区（每种结果形态一个页，按模式切换）---
        self._build_result_area()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(self.result_stack)
        self.splitter.setSizes([660, 400])

        # --- 总布局 ---
        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(self.splitter)

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

        self._bind_shortcuts()
        self._update_tool_state()

    def _build_result_area(self):
        """结果页注册：key 与 MODES 里的 result 字段对应"""
        self.text_result = QTextEdit()
        self.text_result.setPlaceholderText("识别结果会显示在这里……")
        self.text_result.setStyleSheet("font-size: 15px;")

        self.table_result = QTableWidget()
        self.table_result.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_result.setAlternatingRowColors(True)
        self.table_result.setWordWrap(True)
        self.table_result.verticalHeader().setVisible(False)
        self.table_result.setToolTip("识别出的表格，可用「导出文件」保存为 Excel")

        self.result_stack = QStackedWidget()
        self._result_pages = {
            "text": self.text_result,
            "table": self.table_result,
        }
        for page in self._result_pages.values():
            self.result_stack.addWidget(page)

    # ---------- 模式 ----------

    def _on_mode_changed(self, _index: int):
        self.set_mode(self.combo_mode.currentData())

    def set_mode(self, key: str):
        if key not in MODE_BY_KEY:
            key = "basic"
        self.mode = key
        cfg = MODE_BY_KEY[key]

        idx = self.combo_mode.findData(key)
        if idx >= 0 and self.combo_mode.currentIndex() != idx:
            self.combo_mode.blockSignals(True)
            self.combo_mode.setCurrentIndex(idx)
            self.combo_mode.blockSignals(False)

        self.btn_pick.setText(cfg["pick"])
        if cfg["run"]:
            self.btn_run.setText(cfg["run"])
            self.btn_run.show()
        else:
            self.btn_run.hide()

        self.result_stack.setCurrentWidget(self._result_pages[cfg["result"]])
        self._refresh_shortcut_tooltips()
        self._update_tool_state()
        self.statusBar().showMessage(cfg["hint"])

    # ---------- 快捷键 ----------

    def _action_map(self) -> dict:
        """动作键 -> 槽函数。DEFAULT_SHORTCUTS 里的动作键必须在这里有对应实现。"""
        return {
            "open": self.on_pick,
            "capture": self.start_capture,
            "run": self.on_run,
            "copy": self.on_copy,
            "export": self.on_export,
            "fit": self.image_canvas.fit_window,
            "actual": self.image_canvas.actual_size,
            "annot": self._toggle_annot,
            "settings": self.open_settings,
        }

    def _bind_shortcuts(self, mapping: dict | None = None):
        """按用户配置重建全部快捷键（窗口内生效），旧绑定先拆掉。

        用 QShortcut 而不是给按钮设 mnemonic：按钮文字里加 & 会显示下划线，
        且 Alt 组合键不符合 Windows 用户的 Ctrl 习惯。
        """
        mapping = mapping or load_shortcuts()
        self.shortcut_map = mapping

        for sc in getattr(self, "_shortcuts", []):
            sc.setEnabled(False)      # 先禁用，避免与新建的绑定短暂重复触发
            sc.setParent(None)
            sc.deleteLater()
        self._shortcuts = []

        actions = self._action_map()
        for name, seqs in mapping.items():
            slot = actions.get(name)
            if slot is None:          # 配置里出现未知动作键（旧版本残留）时跳过
                continue
            for seq in seqs:
                sc = QShortcut(QKeySequence(seq), self)
                sc.setContext(Qt.ShortcutContext.WindowShortcut)
                sc.activated.connect(slot)
                self._shortcuts.append(sc)

        self._refresh_shortcut_tooltips()

    def _refresh_shortcut_tooltips(self):
        """按钮提示里显示当前绑定，改键 / 切模式后能立刻看到结果。"""
        hints = {name: shortcuts_to_text(seqs)
                 for name, seqs in getattr(self, "shortcut_map", {}).items()}
        cfg = MODE_BY_KEY.get(self.mode, MODE_BY_KEY["basic"])
        pick_key = "capture" if self.mode == "instant" else "open"
        pick_hint = hints.get(pick_key, "")
        self.btn_pick.setToolTip(
            f"{cfg['pick']}（{pick_hint}）" if pick_hint else cfg["pick"])
        if cfg["run"]:
            run_hint = hints.get("run", "")
            self.btn_run.setToolTip(
                f"{cfg['run']}（{run_hint}）" if run_hint else cfg["run"])
        self.btn_copy.setToolTip(f"复制结果（{hints['copy']}）" if hints.get("copy") else "复制结果")
        self.btn_export.setToolTip(
            f"导出文件（{hints['export']}）" if hints.get("export") else "导出文件")
        self.btn_settings.setToolTip(
            f"查看与自定义快捷键（{hints['settings']}）" if hints.get("settings")
            else "查看与自定义快捷键")

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.saved.connect(self._bind_shortcuts)   # 保存后立即生效，无需重启
        dlg.exec()
        self._update_tool_state()

    def _toggle_annot(self):
        """原图 / 识别框图切换（快捷键用）。识别框不可用时不做任何事。"""
        if self.chk_annot.isEnabled():
            self.chk_annot.setChecked(not self.chk_annot.isChecked())

    # ---------- 按钮分发（按注册表）----------

    def on_pick(self):
        name = MODE_BY_KEY[self.mode].get("on_pick")
        if name:
            getattr(self, name)()

    def on_run(self):
        name = MODE_BY_KEY[self.mode].get("on_run")
        if name:
            getattr(self, name)()

    # ---------- 载入图片 ----------

    def on_pick_file(self):
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

        self.image_path = path
        self.last_dir = os.path.dirname(path)
        self._set_image(pil_img, os.path.basename(path))

    def _set_image(self, pil_img, name: str):
        """设置当前图像并重置结果（文件与截图共用）"""
        self.image = pil_img
        self.image_name = name
        self.pixmap_orig = pil_to_qpixmap(pil_img)
        self.pixmap_annot = None
        self.lines = []
        self.table = None

        self.text_result.clear()
        self.table_result.clear()
        self.table_result.setRowCount(0)
        self.table_result.setColumnCount(0)

        # 重置标注开关（避免信号触发多余的刷新）
        self.chk_annot.blockSignals(True)
        self.chk_annot.setChecked(False)
        self.chk_annot.blockSignals(False)

        self.image_canvas.set_image(self.pixmap_orig)
        self._update_tool_state()

        msg = f"已载入：{name}（{pil_img.width}×{pil_img.height}）"
        if max(pil_img.width, pil_img.height) > MAX_SIDE:
            msg += f"｜图片较大，识别时将自动压缩到 {MAX_SIDE}px 以内"
        self.statusBar().showMessage(msg)

    # ---------- 即时识别（截图）----------

    def on_capture_screen(self):
        self.start_capture()

    def start_capture(self):
        """隐藏主窗口 -> 全屏框选 -> 截取区域 -> 自动识别"""
        if self._busy:
            self.statusBar().showMessage("正在识别中，完成后再截图")
            return
        if self.mode != "instant":
            self.set_mode("instant")
        self.hide()
        # 稍等一下，确保主窗口已经从屏幕上消失，否则会把自己截进去
        QTimer.singleShot(160, self._show_capture_overlay)

    def _show_capture_overlay(self):
        try:
            self._overlay = ScreenCaptureOverlay()
        except Exception as exc:            # noqa: BLE001
            self.show()
            QMessageBox.warning(self, "无法截屏", f"{type(exc).__name__}: {exc}")
            return
        self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()
        self._overlay.setFocus()

    def _on_captured(self, pixmap: QPixmap):
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            pil_img = qpixmap_to_pil(pixmap)
        except Exception as exc:            # noqa: BLE001
            QMessageBox.warning(self, "截图失败", f"{type(exc).__name__}: {exc}")
            return

        stamp = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        self.image_path = None              # 截图没有文件路径
        self._set_image(pil_img, f"屏幕截图_{stamp}.png")
        self.statusBar().showMessage(
            f"已截取 {pil_img.width}×{pil_img.height}，正在识别……")
        self.on_run_ocr()

    def _on_capture_cancelled(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.statusBar().showMessage("已取消截图")

    # ---------- 识别 ----------

    def on_run_ocr(self):
        if self.image is None:
            return
        self._set_busy(True, "正在识别……（首次运行需加载模型，请稍候）")

        self.worker = RecognizeWorker(self.image)
        self.worker.done.connect(self.on_recognized)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_run_table(self):
        if self.image is None:
            return
        self._set_busy(True, "正在识别表格……（首次运行需加载表格模型，请稍候）")

        self.worker = TableWorker(self.image)
        self.worker.done.connect(self.on_table_recognized)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_recognized(self, lines: list):
        self._set_busy(False)
        self.lines = lines

        if not lines:
            self.text_result.setPlainText("（未识别到文字）")
            self.statusBar().showMessage("未识别到文字，可换更清晰的图片试试")
            self._update_tool_state()
            return

        # 结果区：只输出识别到的文本（纯文本，不带置信度）
        self.text_result.setPlainText(OCREngine.to_text(lines))

        # 生成标注图并默认显示；失败时降级为「只给文字」，不影响主流程
        note = ""
        try:
            annotated = OCREngine.draw_annotated_image(self.image, lines)
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
        self._update_tool_state()

    def on_table_recognized(self, table: TableResult):
        self._set_busy(False)
        self.table = table

        if not table.rows:
            self.statusBar().showMessage(
                "未识别到表格结构，可换更清晰的表格图片试试")
            self._update_tool_state()
            return

        self._fill_table(table.rows)
        self.statusBar().showMessage(
            f"表格识别完成：{table.n_rows} 行 × {table.n_cols} 列"
            "（可用「导出文件」保存为 Excel）")
        self._update_tool_state()

    def _fill_table(self, rows: list):
        n_cols = max((len(r) for r in rows), default=0)
        t = self.table_result
        t.clear()
        t.setRowCount(len(rows))
        t.setColumnCount(n_cols)
        t.setHorizontalHeaderLabels([f"列 {i + 1}" for i in range(n_cols)])

        for r, row in enumerate(rows):
            for c in range(n_cols):
                value = row[c] if c < len(row) else ""
                t.setItem(r, c, QTableWidgetItem(value))

        t.resizeColumnsToContents()
        # 长文本列别把窗口撑爆，超宽的列回到固定宽度
        for c in range(n_cols):
            if t.columnWidth(c) > 260:
                t.setColumnWidth(c, 260)
        t.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)

    def on_failed(self, msg: str):
        self._set_busy(False)
        self.statusBar().showMessage("识别失败")
        QMessageBox.critical(self, "识别失败", msg)
        self._update_tool_state()

    def _set_busy(self, busy: bool, msg: str = ""):
        """统一管理识别中的界面反馈：按钮文字、进度条、忙碌光标"""
        self._busy = busy
        if busy:
            self.btn_pick.setEnabled(False)
            self.btn_run.setEnabled(False)
            self.btn_run.setText("识别中…")
            self.progress.show()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._cursor_overridden = True
            self.statusBar().showMessage(msg)
        else:
            self.btn_pick.setEnabled(True)
            cfg = MODE_BY_KEY[self.mode]
            if cfg["run"]:
                self.btn_run.setText(cfg["run"])
            self.progress.hide()
            if self._cursor_overridden:
                QApplication.restoreOverrideCursor()
                self._cursor_overridden = False

    # ---------- 图片显示 ----------

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

    def _update_tool_state(self):
        """按当前模式与数据决定各按钮可用性"""
        has_src = self.image is not None
        cfg = MODE_BY_KEY[self.mode]

        self.btn_fit.setEnabled(has_src)
        self.btn_actual.setEnabled(has_src)
        self.chk_annot.setEnabled(self.pixmap_annot is not None)

        if cfg["run"]:
            self.btn_run.setEnabled(has_src and not self._busy)

        if cfg["result"] == "table":
            has_result = bool(self.table and self.table.rows)
        else:
            has_result = bool(self.lines)
        self.btn_copy.setEnabled(has_result)
        self.btn_export.setEnabled(has_result)

    # ---------- 结果落地 ----------

    def on_copy(self):
        if MODE_BY_KEY[self.mode]["result"] == "table":
            if not (self.table and self.table.rows):
                return
            QApplication.clipboard().setText(self.table.to_tsv())
            self.statusBar().showMessage(
                "表格已复制（制表符分隔，可直接粘进 Excel）")
            return

        if not self.lines:
            return
        QApplication.clipboard().setText(OCREngine.to_text(self.lines))
        self.statusBar().showMessage("已复制到剪贴板")

    def on_export(self):
        cfg = MODE_BY_KEY[self.mode]
        stem = os.path.splitext(self.image_name)[0] or "ocr_result"

        if cfg["result"] == "table":
            if not (self.table and self.table.rows):
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "导出表格",
                os.path.join(self.last_dir, f"{stem}_表格.xlsx"),
                "Excel 工作簿 (*.xlsx)")
            if not path:
                return
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            try:
                TableEngine.save_xlsx(self.table.rows, path)
            except Exception as exc:        # noqa: BLE001
                QMessageBox.critical(self, "导出失败",
                                     f"{type(exc).__name__}: {exc}")
                return
            self.last_dir = os.path.dirname(path)
            self.statusBar().showMessage(f"已导出：{os.path.basename(path)}")
            return

        if not self.lines:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", os.path.join(self.last_dir, f"{stem}.txt"),
            "文本文件 (*.txt);;Markdown 文件 (*.md)"
        )
        if not path:
            return
        text = OCREngine.to_text(self.lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.last_dir = os.path.dirname(path)
        self.statusBar().showMessage(f"已导出：{os.path.basename(path)}")

    # ---------- 窗口状态持久化 ----------

    def _restore_ui_state(self):
        prefs = load_ui_prefs()
        self.last_dir = prefs["last_dir"] or ""
        mode = prefs["mode"] if prefs["mode"] in MODE_BY_KEY else "basic"
        self.set_mode(mode)

        if not prefs["remember"]:
            return

        store = _settings()
        geo = store.value("ui/geometry")
        if geo:
            self.restoreGeometry(geo)
            if not self._geometry_visible():
                # 上次是在已拔掉的外接屏上用的：回到默认尺寸并居中
                self.resize(1080, 680)
                self._center_on_primary()
        splitter_state = store.value("ui/splitter")
        if splitter_state:
            self.splitter.restoreState(splitter_state)

    def _geometry_visible(self) -> bool:
        frame = self.frameGeometry()
        return any(frame.intersects(s.availableGeometry())
                   for s in QGuiApplication.screens())

    def _center_on_primary(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        self.move(avail.center() - self.rect().center())

    def _save_ui_state(self):
        if not load_ui_prefs()["remember"]:
            return
        store = _settings()
        store.setValue("ui/geometry", self.saveGeometry())
        store.setValue("ui/splitter", self.splitter.saveState())
        store.setValue("ui/last_dir", self.last_dir)
        store.setValue("ui/mode", self.mode)
        store.sync()

    def closeEvent(self, event):
        self._save_ui_state()
        super().closeEvent(event)

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


def _make_table_sample(path: str) -> None:
    """自检用的合成表格：3×3 有框线，结构清晰，识别结果可预期。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (520, 220), "white")
    draw = ImageDraw.Draw(img)
    font = OCREngine.load_font(22)
    x0, y0, cw, ch = 20, 20, 160, 60
    for r in range(3):
        for c in range(3):
            draw.rectangle([x0 + c * cw, y0 + r * ch,
                            x0 + (c + 1) * cw, y0 + (r + 1) * ch],
                           outline="black", width=2)
            draw.text((x0 + c * cw + 12, y0 + r * ch + 18),
                      f"R{r}C{c}", fill="black", font=font)
    img.save(path)


def _selftest() -> int:
    """无界面自检：文字识别 + 表格识别各跑一遍。

    用于验证「打包后的 exe」能否真正加载模型并识别（GUI 程序无控制台，
    故把结果写入 %TEMP%/ocr_selftest.txt，并用退出码表示成败）。

    退出码：0 = 两项均通过；1 = 未识别到文字；2 = 抛出异常；3 = 表格未识别。
    """
    import tempfile

    from PIL import Image, ImageDraw

    tmp = tempfile.gettempdir()
    out_path = os.path.join(tmp, "ocr_selftest.txt")
    report = []
    code = 0
    try:
        # ---- 文字识别 ----
        img = Image.new("RGB", (640, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((24, 24), "OCR 自检 2026", fill="black",
                  font=OCREngine.load_font(48))
        draw.text((24, 92), "Hello 12345", fill="black",
                  font=OCREngine.load_font(38))
        img_path = os.path.join(tmp, "ocr_selftest_input.png")
        img.save(img_path)

        lines = OCREngine().recognize(img_path)
        report.append(f"TEXT lines={len(lines)}")
        report.append(" | ".join(line.text for line in lines))
        if not lines:
            code = 1

        # ---- 表格识别 ----
        table_path = os.path.join(tmp, "ocr_selftest_table.png")
        _make_table_sample(table_path)
        table = TableEngine().recognize(table_path)
        report.append(f"TABLE rows={table.n_rows} cols={table.n_cols}")
        report.append(table.to_tsv())
        if table.n_rows < 3 or table.n_cols < 3:
            code = code or 3
    except Exception as exc:  # noqa: BLE001 - 自检需兜住一切异常并回报
        import traceback

        report.append(f"FAIL {type(exc).__name__}: {exc}")
        report.append("--- traceback ---")
        report.append(traceback.format_exc())

        # 附带 paddlex 的依赖判定结果，便于定位打包后「依赖缺失」的真实原因
        try:
            from paddlex.utils import deps as _deps

            report.append("--- paddlex 依赖可用性 ---")
            for _name in sorted(_deps.DEP_SPECS):
                try:
                    report.append(f"{_name}: {_deps.is_dep_available(_name)}"
                                  f" (ver={_deps.get_dep_version(_name)})")
                except Exception as _e2:  # noqa: BLE001
                    report.append(f"{_name}: ERR {type(_e2).__name__}: {_e2}")
        except Exception as _e2:  # noqa: BLE001
            report.append(f"依赖诊断本身失败: {type(_e2).__name__}: {_e2}")
        code = 2

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    return code


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
    # 打包运行时：把内置模型释放到用户缓存（首次启动一次性动作）
    _ensure_bundled_models()

    # --selftest：无界面自检（不启动 GUI），供打包后验证与自动化测试使用
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    main()
