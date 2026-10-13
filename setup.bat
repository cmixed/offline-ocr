@echo off
REM ============================================================
REM  OCR 小软件 —— 一键环境搭建脚本
REM  用法：双击本文件，或在命令行运行 setup.bat
REM  作用：创建虚拟环境 -> 安装依赖 -> 预下载 OCR 模型
REM ============================================================
chcp 65001 >nul
setlocal

echo ============================================
echo   OCR 小软件 环境搭建
echo ============================================
echo.

REM ---- 1. 定位 Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9~3.13
    echo        下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 检查 Python 版本...
python --version

REM ---- 2. 创建虚拟环境 ----
if not exist ".venv" (
    echo [2/4] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
) else (
    echo [2/4] 虚拟环境 .venv 已存在，跳过创建
)

REM ---- 3. 安装依赖 ----
echo [3/4] 安装依赖（首次可能较慢，请耐心等待）...

REM 先升级 pip
.venv\Scripts\python.exe -m pip install --upgrade pip

REM 安装 PaddlePaddle CPU 版（必须用官方镜像）
echo       正在安装 PaddlePaddle CPU 版（体积较大）...
.venv\Scripts\python.exe -m pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 (
    echo [错误] PaddlePaddle 安装失败
    pause
    exit /b 1
)

REM 补装 PaddlePaddle 的遗漏依赖（setuptools / chardet）
echo       正在补装遗漏依赖（setuptools / chardet）...
.venv\Scripts\python.exe -m pip install "setuptools>=84.0.0" "chardet>=7.6.0"

REM 安装其余依赖（paddleocr、PySide6 等）
echo       正在安装 paddleocr、PySide6 等依赖...
.venv\Scripts\python.exe -m pip install paddleocr==3.2.0 "PySide6>=6.6" "opencv-python>=4.8" "Pillow>=10.0" "pyinstaller>=6.0"

REM ---- 4. 预下载模型（加快首次运行、支持离线使用）----
echo [4/4] 预下载 OCR 模型（约 20MB，首次较慢）...
.venv\Scripts\python.exe src\download_models.py
if errorlevel 1 (
    echo [提示] 模型预下载未完成，不影响使用：首次识别时会自动重试下载。
)

echo.
echo ============================================
echo   环境搭建完成！
echo   测试识别：.venv\Scripts\python.exe test\test_ocr.py test\test_demo.png
echo ============================================
pause
