@echo off
setlocal
cd /d "%~dp0"

if exist "dist\test2.exe" (
    start "" "dist\test2.exe"
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0app.py"
    exit /b 0
)

py -3 "%~dp0app.py"
if errorlevel 1 (
    echo 未找到 Python 3，请先安装 Python 或使用 dist\test2.exe。
    pause
)
endlocal
