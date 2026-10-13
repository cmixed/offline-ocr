# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— OCR 小软件

形态选择：--onedir（而非 onefile）
  - 启动更快（无需每次解包到临时目录）
  - 合规 LGPLv3：PySide6 的 .dll/.pyd 以独立文件存在，便于用户替换

模型策略：把 PP-OCRv5 mobile 模型随包分发，
  首次运行时由程序复制到用户缓存 (~/.paddlex/official_models/)，
  之后完全离线可用。见 src/main.py 的 _ensure_bundled_models()。
"""
import os
from PyInstaller.utils.hooks import (
    collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata,
)

# ---------------- 数据文件 ----------------
datas = []

# 【关键】paddlex 在运行时用 importlib.metadata 判断各依赖「是否已安装」
# （paddlex/utils/deps.py -> is_dep_available -> importlib.metadata.version）。
# OCR 管线被 @pipeline_requires_extra("ocr", alt="ocr-core") 装饰，
# 要求 ocr-core 依赖集（imagesize / opencv-contrib-python / pyclipper /
# pypdfium2 / shapely）全部可用。PyInstaller 默认不打包包元数据（*.dist-info），
# 会导致这些包被误判为「未安装」，报错：
#   A dependency error occurred during pipeline creation
# 故把全部已安装分发的元数据一并收集（纯文本，体积可忽略）。
from importlib.metadata import distributions as _distributions

_seen_meta = set()
for _dist in _distributions():
    _name = _dist.metadata.get("Name")
    if not _name or _name in _seen_meta:
        continue
    _seen_meta.add(_name)
    try:
        datas += copy_metadata(_name)
    except Exception:
        # 个别分发的名字可能不规范，跳过即可（不影响主流程）
        pass

# paddlex 的 315 个 yaml 配置 + 其他资源（模型结构、预处理配置等）
datas += collect_data_files("paddlex")

# 应用图标（main.py 打包后从 _MEIPASS/assets 读取）
datas += [
    ("assets/icon.ico", "assets"),
    ("assets/icon.png", "assets"),
]

# 内置 OCR 模型（约 22MB）：随包分发，首次运行复制到用户缓存目录
_models_src = os.path.join(os.path.expanduser("~"), ".paddlex", "official_models")
for _m in ("PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec"):
    _p = os.path.join(_models_src, _m)
    if os.path.isdir(_p):
        datas.append((_p, os.path.join("paddlex_models", "official_models", _m)))

# ---------------- 二进制动态库 ----------------
# PaddlePaddle 的 C++ 核心库（libpaddle.pyd 等）必须显式收集
binaries = collect_dynamic_libs("paddle")

# ---------------- 隐藏导入 ----------------
hiddenimports = []
# paddlex / paddleocr 大量使用动态导入，静态分析扫不到，需整包收集
hiddenimports += collect_submodules("paddlex")
hiddenimports += collect_submodules("paddleocr")
hiddenimports += [
    "paddle",
    "paddle.base",
    "paddle.base.libpaddle",
    "paddle.utils",
    "PIL._tkinter_finder",  # 规避 PIL 的 tkinter 探测告警
]

# ---------------- 排除体积大户 / 无关模块 ----------------
excludes = [
    # PySide6 中本项目未使用的重型模块
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml",
    "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtNfc",
    "PySide6.QtOpenGL", "PySide6.QtPositioning", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
    "PySide6.QtStateMachine", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    # 科学计算 / 开发工具（本程序不依赖）
    "matplotlib", "tkinter", "IPython", "pytest", "notebook", "jupyter",
    "scipy", "sympy", "numba", "torch", "tensorflow",
    # modelscope 中 OCR 流程用不到的重型子包。
    # 依据运行诊断：实际只加载 modelscope.hub / modelscope.utils（modelscope.models 加载数为 0），
    # 而这些 CV/NLP/音频模型定义体量巨大，且部分会牵连 paddle.jit.sot 导致打包分析崩溃。
    "modelscope.models", "modelscope.msdatasets", "modelscope.trainers",
    "modelscope.preprocessors", "modelscope.exporters", "modelscope.metrics",
    "modelscope.pipelines", "modelscope.ops",
    # Paddle 的符号化编译（SOT）：纯推理完全用不到，
    # 其导入在 PyInstaller 依赖分析阶段极不稳定（首次构建即崩于此）。
    "paddle.jit.sot",
]

# ---------------- 分析与打包 ----------------
a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OCR小软件",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压缩易被杀软误报，且对 paddle 大 dll 收益有限
    console=False,      # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OCR小软件",
)
