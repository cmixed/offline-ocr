# OCR 小软件

<img src="assets/icon.png" width="88" align="right" alt="应用图标">

> 一个本地离线运行的 OCR 图片识别小软件，专注「垂直场景」，从普通图片识别起步。

## 简介

把图片里的文字提取出来，拖图、点击、出文字、可复制可导出。全程本地运行，数据不出本机。

- **技术栈**：Python + PySide6 + PaddleOCR
- **引擎**：PaddleOCR（PP-OCRv5 mobile 轻量模型）
- **平台**：Windows

## 功能

- [x] 普通图片 / 截图文字识别
- [x] 支持 17 种图片格式（png / jpg / jpeg / jfif / bmp / webp / tif / tiff / gif / ico / tga / ppm / pgm / pbm / pnm / xbm / xpm）
- [x] 命令行识别：图片 → 文本
- [x] 可视化：生成标注图 / HTML 报告页
- [x] GUI 图形界面（拖拽/选图、标注框、复制、导出）
- [x] 图片滚轮缩放 / 鼠标拖动平移 / 适应窗口 / 原始大小
- [x] 拖拽图片文件进窗口（带高亮反馈）
- [x] 原图 ↔ 标注图一键切换
- [x] 识别进度反馈（进度条 + 忙碌光标，不再「以为卡死」）
- [x] 模型预下载脚本（可离线使用，首次无需联网）
- [x] 边界处理：中文路径 / 超大图自动压缩 / 损坏文件友好报错
- [x] 应用图标（由脚本生成，可复现）
- [ ] 快捷键、记住窗口与目录设置
- [ ] 截图即时识别（垂直场景，规划中）

## 支持的图片格式

支持 **17 种**常见图片格式，**不限 PNG**：

| 类型 | 扩展名 |
|------|--------|
| 最常用 | `.png` `.jpg` `.jpeg` `.jfif` `.bmp` `.webp` |
| 扫描 / 传真件 | `.tif` `.tiff` |
| 其他 | `.gif` `.ico` `.tga` `.ppm` `.pgm` `.pbm` `.pnm` `.xbm` `.xpm` |

设计上有一点值得说明：**「载入显示」与「文字识别」共用同一套解码逻辑（PIL）**。
这样不会出现「界面能显示、识别引擎却打不开」的格式错位（例如 SVG、PDF —— Qt 能渲染，OCR 无法识别）。
一句话：**界面上能看到的图，一定能识别。**

- 选择文件时若遇到不常见格式，对话框里的「所有文件 (*)」可强制尝试
- 拖拽时若拖入的文件都不在支持列表内，会明确提示，而不是静默失败
- 格式清单的唯一来源是 `src/ocr_engine.py` 的 `SUPPORTED_EXTS`，文件选择框的过滤器由它自动生成，不会两处不一致

> 注：`.ico` 受格式规范限制最大 256×256，更大的图会被降采样；`.gif` / `.tiff` 若为多帧 / 多页，只读取第一帧。

## 从零搭建（环境可复现）

### 前置要求

- Windows 10/11（64 位）
- Python 3.9 ~ 3.13（64 位）

### 方式一：一键脚本（推荐）

双击项目根目录的 `setup.bat`，自动完成环境搭建。

### 方式二：手动搭建

```bat
REM 1. 创建虚拟环境
python -m venv .venv

REM 2. 安装 PaddlePaddle（必须用官方镜像，PyPI 无最新 CPU 版）
.venv\Scripts\python.exe -m pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

REM 3. 补装遗漏依赖（PaddlePaddle 3.2.1 的坑）
.venv\Scripts\python.exe -m pip install "setuptools>=84.0.0" "chardet>=7.6.0"

REM 4. 安装其余依赖
.venv\Scripts\python.exe -m pip install paddleocr==3.2.0 "PySide6>=6.6" "opencv-python>=4.8"
```

> 如需完全一致的环境，可用 `requirements.lock`（pip freeze 全量锁定）：
> `.venv\Scripts\python.exe -m pip install -r requirements.lock`

### 预下载 OCR 模型（可选，推荐）

```bat
.venv\Scripts\python.exe src\download_models.py
```

把模型提前缓存到 `~/.paddlex/official_models/`（约 20MB），之后**完全离线**也能识别。
不预下载也可以 —— 首次识别时会自动下载，这个脚本只是把这步提前。
`setup.bat` 已自动包含此步。

## 使用

### 1. 图形界面（推荐）

```bat
.venv\Scripts\python.exe src\main.py
```

把图片拖进窗口 → 点「开始识别」→ 右侧显示文字，左侧图片上画出识别框。
支持一键复制结果、导出 TXT / Markdown。

**界面操作：**

| 操作 | 说明 |
|------|------|
| 拖入图片 | 把图片文件从文件夹拖进窗口即可载入（悬停时边框变绿提示可松手），也可点「选择图片」 |
| 滚轮 | 缩放图片（5% ~ 800%） |
| 按住鼠标拖动 | 放大后可按住左键拖动画面看细节（光标变手型），不用去拖滚动条 |
| 「显示识别框」 | 勾选显示标注图（绿框 + 文字），取消显示原图，切换时保留缩放 |
| 「适应窗口」/「原始大小」 | 一键切换查看比例，右侧实时显示当前百分比 |
| 识别中 | 按钮变「识别中…」，状态栏出现进度条，光标变忙碌态 |

> 识别结果只输出图片中的文字本身，不附带置信度等额外信息。

### 2. 命令行识别

```bat
.venv\Scripts\python.exe test\test_ocr.py test\test_demo.png
```

`test/` 目录下放着两张示例图，可以直接拿来试：

| 文件 | 内容 |
|------|------|
| `test_image.png` | 基础测试图（2 行中文 + 数字） |
| `test_demo.png` | 混合内容测试图（7 行：标题 / 中文正文 / 数字 / 邮箱 / 中英混合 ID） |

输出（只输出文本本身，不带置信度等附加信息）：
```
产品周报 · 第二季度
本季度累计新增用户 12,480 人，环比增长 23.5%。
其中移动端占比 68%，PC 端占比 32%。
```

### 3. 生成标注图

```bat
.venv\Scripts\python.exe test\visualize_ocr.py test\test_demo.png
```
生成 `result_vis.jpg`：绿框标出文字位置，红字显示识别到的文字。

### 4. 生成 HTML 可视化报告

```bat
.venv\Scripts\python.exe test\report_ocr.py test\test_demo.png
```
生成 `ocr_report.html`：原图 / 标注图对比 + 识别文本表 + 结构化 JSON，图片以 base64 内嵌，单文件可直接分享。

> 上面两个脚本的输出文件默认生成在**当前工作目录**；想直接放进 `test/`，把输出路径作为第二个参数传入即可，例如：
> `.venv\Scripts\python.exe test\visualize_ocr.py test\test_demo.png test\result_vis.png`

> 首次运行会自动下载 OCR 模型（约 20MB）到 `~/.paddlex/official_models/`，之后离线可用。

### 5. 边界场景测试

```bat
.venv\Scripts\python.exe test\test_edge_cases.py
```

覆盖 5 类场景：正常图 / 无文字图 / 损坏文件 / 超大图 / 中文路径，全部通过会打印 `5/5 项通过`。

### 6. 格式支持测试

```bat
.venv\Scripts\python.exe test\test_formats.py
```

逐一验证 `SUPPORTED_EXTS` 里每种格式的「载入 + 识别」都正常，并检查扩展名判定（含大小写不敏感），全部通过会打印 `36/36 项通过`。

## 目录结构

```
ocrapp/
├── src/                   # 正式代码
│   ├── main.py            # GUI 主程序（PySide6）
│   ├── ocr_engine.py      # OCR 引擎封装
│   └── download_models.py # 模型预下载脚本
├── test/                  # 测试脚本、测试数据与运行产物
│   ├── test_ocr.py        # 命令行识别
│   ├── visualize_ocr.py   # 生成标注图
│   ├── report_ocr.py      # 生成 HTML 报告
│   ├── test_edge_cases.py # 边界场景测试（5 类）
│   ├── test_formats.py    # 格式支持测试（17 种扩展名）
│   ├── test_image.png     # 示例图（基础，2 行）
│   ├── test_demo.png      # 示例图（7 行混合内容）
│   ├── result_vis.png     # 标注图产物
│   ├── ocr_report.html    # HTML 报告产物
│   └── gui_*.png          # GUI 界面截图
├── assets/                # 应用图标
│   ├── icon.ico           # 多尺寸 Windows 图标（打包时使用）
│   ├── icon.png           # 256×256 PNG（README / 非 Windows 平台）
│   └── make_icon.py       # 图标生成脚本（保证图标可复现）
├── requirements.txt       # 依赖清单（含版本说明）
├── requirements.lock      # 全量锁定版本（pip freeze）
├── setup.bat              # 一键安装脚本
├── OCR小软件可行性计划.md   # 技术方案与四阶段路线图
├── OCR项目进度跟踪.md       # 进度、待完善项、优化方向
├── .gitignore
└── README.md
```

> 说明：`test/` 目录同时存放测试脚本、示例图片和运行产物。其中示例图片会被提交到仓库（便于复现识别结果），运行产物（`result_vis.*`、`ocr_report.html`、`gui_*.png`）已在 `.gitignore` 中排除。

## 已知问题 / 踩坑

- `paddleocr==3.2.1` 版本不存在，正确版本是 `3.2.0`
- PaddlePaddle 3.2.1 遗漏 `setuptools` 依赖，`import paddle` 会报错，需手动补装
- `paddlex` 依赖 `chardet`，官方镜像无此包，需先装
- PaddleOCR 3.x 使用新 API（`text_detection_model_name` + `predict()`），网上旧教程的 `use_angle_cls`/`ocr()` 已废弃

### 已主动处理的边界情况

- **中文 / 含空格路径**：统一「PIL 读图 → ndarray」再送入识别，规避路径兼容问题
- **超大图**（最长边 > 4000px）：自动等比压缩后识别，识别框坐标会还原回原图，标注位置依然准确
- **损坏文件 / 非图片**：抛出可读提示「无法识别的图片格式」，程序不会崩溃
- **无文字图片**：提示「未识别到文字」，界面状态正常
- **标注图生成失败**：降级为「只显示文字」，不影响识别结果的使用
- **格式错位**：载入与识别共用同一套 PIL 解码，杜绝「能显示却识别不了」的格式（如 SVG、PDF）
- **拖入非图片**：拖拽时先按扩展名筛选，没有可识别的图片就明确提示，不会静默失败

## 许可证

本项目以 **MIT 许可证** 发布，详见 [LICENSE](LICENSE)。

界面框架选用 **PySide6**（LGPLv3）而非 PyQt6（GPL-3.0-only），从而允许本项目以宽松的 MIT 许可证开源。
所有第三方组件的署名与许可证信息，见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

## 进度

详见《OCR项目进度跟踪.md》
