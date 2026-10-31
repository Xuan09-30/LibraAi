@echo off
title Project Libra Desktop Assistant
cd /d "%~dp0"
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "ui\gui.py"
) else (
    cd /d "C:\Users\chenx\Desktop\LIBRA\LibraAi"
    start "" "venv\Scripts\pythonw.exe" "ui\gui.py"
)
echo.
echo ======================================================
echo   [Project Libra Desktop Assistant Online]
echo   - Interactive Desktop GUI running on Windows 11
echo   - Local Web UI: http://localhost:8765
echo ======================================================
timeout /t 2 >nul
