@echo off
setlocal
cd /d "%~dp0"
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name test2 --distpath dist --workpath build app.py
if errorlevel 1 (
    echo Build failed. Install PyInstaller with: py -3 -m pip install pyinstaller
    pause
) else (
    echo Build complete: dist\test2.exe
)
endlocal
