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
import shutil
import sys

# 保证能 import 同目录的 ocr_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QScrollArea, QCheckBox, QProgressBar, QDialog, QDialogButtonBox,
    QGroupBox, QGridLayout, QKeySequenceEdit,
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QPixmap, QImage, QFont, QIcon, QKeySequence, QShortcut

from ocr_engine import (
    MAX_SIDE, OCREngine, OCRLine, SUPPORTED_EXTS,
    file_dialog_filter, is_supported_ext,
)

# 全局引擎（模型只加载一次）
engine = OCREngine()

PLACEHOLDER = "把图片拖到这里\n\n或点击「选择图片」"

# ---------- 快捷键定义与持久化 ----------
#
# DEFAULT_SHORTCUTS 是唯一来源：默认值、绑定、设置面板、测试都读它。
# 结构：(动作键, 说明, 默认按键元组)
# 一个动作可以有多个按键（例如 Ctrl+Enter 同时覆盖主键盘与小键盘回车）。
DEFAULT_SHORTCUTS = [
    ("open", "选择图片", ("Ctrl+O",)),
    ("run", "开始识别", ("Ctrl+Enter", "Ctrl+Return")),
    ("copy", "复制识别结果（Ctrl+C 留给结果框自己）", ("Ctrl+Shift+C",)),
    ("export", "导出为 TXT / Markdown", ("Ctrl+S",)),
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
        self.saved.emit(mapping)
        self.accept()


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

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setToolTip("查看与自定义快捷键")
        self.btn_settings.clicked.connect(self.open_settings)

        toolbar = QHBoxLayout()
        for b in (self.btn_open, self.btn_run, self.btn_copy, self.btn_export):
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

        self._bind_shortcuts()
        self._update_tool_state()

    # ---------- 快捷键 ----------

    def _action_map(self) -> dict:
        """动作键 -> 槽函数。DEFAULT_SHORTCUTS 里的动作键必须在这里有对应实现。"""
        return {
            "open": self.on_open,
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
        """按钮提示里显示当前绑定，改键后能立刻看到结果。"""
        hints = {name: shortcuts_to_text(seqs)
                 for name, seqs in getattr(self, "shortcut_map", {}).items()}
        for btn, name, text in (
            (self.btn_open, "open", "选择图片"),
            (self.btn_run, "run", "开始识别"),
            (self.btn_copy, "copy", "复制结果"),
            (self.btn_export, "export", "导出文件"),
        ):
            tip = f"{text}（{hints[name]}）" if hints.get(name) else text
            btn.setToolTip(tip)
        self.btn_settings.setToolTip(
            f"查看与自定义快捷键（{hints['settings']}）" if hints.get("settings")
            else "查看与自定义快捷键")

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.saved.connect(self._bind_shortcuts)   # 保存后立即生效，无需重启
        if dlg.exec() and self.shortcut_map.get("settings"):
            self.statusBar().showMessage(
                f"快捷键已更新（设置面板：{shortcuts_to_text(self.shortcut_map['settings'])}）")

    def _toggle_annot(self):
        """原图 / 识别框图切换（快捷键用）。识别框不可用时不做任何事。"""
        if self.chk_annot.isEnabled():
            self.chk_annot.setChecked(not self.chk_annot.isChecked())

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


def _selftest() -> int:
    """无界面自检：程序生成一张文字图，跑一次完整识别流程。

    用于验证「打包后的 exe」能否真正加载模型并识别（GUI 程序无控制台，
    故把结果写入 %TEMP%/ocr_selftest.txt，并用退出码表示成败）。

    退出码：0 = 成功；1 = 未识别到文字；2 = 抛出异常。
    """
    import tempfile

    from ocr_engine import OCREngine

    out_path = os.path.join(tempfile.gettempdir(), "ocr_selftest.txt")
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (640, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.text((24, 24), "OCR 自检 2026", fill="black",
                  font=OCREngine.load_font(48))
        draw.text((24, 92), "Hello 12345", fill="black",
                  font=OCREngine.load_font(38))
        img_path = os.path.join(tempfile.gettempdir(), "ocr_selftest_input.png")
        img.save(img_path)

        lines = OCREngine().recognize(img_path)
        text = " | ".join(line.text for line in lines)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"OK lines={len(lines)}\n{text}\n")
        return 0 if lines else 1
    except Exception as exc:  # noqa: BLE001 - 自检需兜住一切异常并回报
        import traceback

        lines = [f"FAIL {type(exc).__name__}: {exc}", "", "--- traceback ---",
                 traceback.format_exc()]
        # 附带 paddlex 的依赖判定结果，便于定位打包后「依赖缺失」的真实原因
        try:
            from paddlex.utils import deps as _deps

            lines.append("--- paddlex 依赖可用性 ---")
            for _name in sorted(_deps.DEP_SPECS):
                try:
                    lines.append(f"{_name}: {_deps.is_dep_available(_name)}"
                                 f" (ver={_deps.get_dep_version(_name)})")
                except Exception as _e2:  # noqa: BLE001
                    lines.append(f"{_name}: ERR {type(_e2).__name__}: {_e2}")
        except Exception as _e2:  # noqa: BLE001
            lines.append(f"依赖诊断本身失败: {type(_e2).__name__}: {_e2}")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return 2


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
