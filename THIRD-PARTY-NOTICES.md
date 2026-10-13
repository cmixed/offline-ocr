# 第三方组件许可声明（Third-Party Notices）

本项目（OCR 小软件）自身以 **MIT 许可证** 发布（见 `LICENSE`）。
但它依赖并使用了一系列优秀的开源组件，这些组件各自遵循其自身的许可证。
本文件汇总这些组件的名称、版本、许可证与用途，以尽到署名与合规义务。

> 版本号用于说明本项目实际测试通过的组合，详见 `requirements.txt` / `requirements.lock`。

## 一、运行时依赖（随程序一起分发）

| 组件 | 版本 | 许可证 | 用途 |
|------|------|--------|------|
| [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) | 3.2.1 | Apache-2.0 | 深度学习推理框架 |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 3.2.0 | Apache-2.0 | OCR 文字检测与识别 |
| [PaddleX](https://github.com/PaddlePaddle/PaddleX) | （随 PaddleOCR） | Apache-2.0 | OCR 模型管理 |
| [PySide6](https://www.qt.io/qt-for-python)（Qt for Python） | 6.12.0 | LGPLv3 / GPLv3 / 商业 | 图形界面框架 |
| [shiboken6](https://www.qt.io/qt-for-python) | 6.12.0 | LGPLv3 / GPLv3 / 商业 | PySide6 绑定生成器运行时 |
| [NumPy](https://numpy.org/) | — | BSD-3-Clause | 数值/数组计算 |
| [Pillow](https://python-pillow.org/) | — | MIT-CMU (HPND) | 图片解码与绘制 |
| [opencv-python](https://github.com/opencv/opencv-python) | — | Apache-2.0 | 图像预处理 |
| [chardet](https://github.com/chardet/chardet) | — | LGPL-2.1 | 字符编码检测（paddlex 依赖） |
| [setuptools](https://github.com/pypa/setuptools) | — | MIT | 打包/元数据（paddle 运行时依赖） |

## 二、构建期工具（不随产物分发）

| 组件 | 版本 | 许可证 | 用途 |
|------|------|--------|------|
| [PyInstaller](https://pyinstaller.org/) | — | GPL-2.0-with-exception | 打包为 Windows 可执行文件 |

> PyInstaller 用于“构建”可执行文件，其自身代码不会成为产物的一部分；其打包引导程序遵循 GPL-2.0-with-exception，该例外条款明确允许将打包产物以任意许可证发布。

## 三、OCR 模型

| 模型 | 来源 | 许可证 |
|------|------|--------|
| PP-OCRv5_mobile_det / PP-OCRv5_mobile_rec | PaddleOCR 官方模型库 | Apache-2.0 |

模型在首次运行时下载到 `~/.paddlex/official_models/`，也可通过 `src/download_models.py` 预下载。

## 四、关于 LGPLv3 组件（PySide6 / shiboken6）的合规说明

PySide6 与 shiboken6 默认以 **LGPLv3** 授权。为遵守 LGPLv3，本项目在分发打包产物时遵循以下原则：

1. **动态链接**：PySide6 相关库以动态链接库（.dll/.pyd）形式随程序分发，不进行静态链接或修改。
2. **允许替换**：不锁定、不阻止用户替换上述 LGPL 库文件（用户可自行替换为兼容版本）。
3. **提供许可证副本**：随源码仓库一并提供本声明文件；发布打包产物时建议同目录附带本文件与 LGPLv3 全文。
4. **不修改上游代码**：本项目未修改 PySide6 / shiboken6 / Qt 的源代码。

> 若你选择以 GPLv3 或商业授权方式使用 PySide6，则可不受上述 LGPL 约束；本项目默认按 LGPLv3 合规使用。

## 五、许可证全文获取

各组件许可证全文可从对应项目仓库或其安装包内的 `LICENSE` / `COPYING` 文件获取：

- Apache-2.0：<https://www.apache.org/licenses/LICENSE-2.0>
- MIT：<https://opensource.org/licenses/MIT>
- BSD-3-Clause：<https://opensource.org/licenses/BSD-3-Clause>
- LGPLv3：<https://www.gnu.org/licenses/lgpl-3.0.html>
- GPLv3：<https://www.gnu.org/licenses/gpl-3.0.html>

---

如对许可合规有任何疑问，请以各上游项目的官方说明为准。
