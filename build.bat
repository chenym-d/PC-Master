@echo off
REM ============================================================
REM  PCM build script (one-click package)
REM  1) Install all dependencies (bundled into the exe)
REM  2) Package with PyInstaller into a single PCM.exe
REM  Output: dist\PCM.exe
REM
REM  NOTE: uses Aliyun PyPI mirror. The Tsinghua mirror
REM  (pypi.tuna.tsinghua.edu.cn) returns HTTP 403 on this
REM  machine, which makes pip report "from versions: none".
REM ============================================================

echo [1/2] Installing dependencies (only needed once)...
pip install -i https://mirrors.aliyun.com/pypi/simple/ pillow requests "qrcode[pil]" speedtest-cli send2trash psutil pyinstaller
if errorlevel 1 (
    echo Failed to install dependencies. Please check network.
    pause
    exit /b 1
)

echo [2/2] Packaging with PyInstaller...
pyinstaller --onefile --windowed --clean --name PCM --icon=app.ico main.py
if errorlevel 1 (
    echo Packaging failed.
    pause
    exit /b 1
)

echo.
echo Done! Output: dist\PCM.exe (single file, portable, no installs needed)
pause
