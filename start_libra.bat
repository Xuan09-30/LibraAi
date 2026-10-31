@echo off
title Project Libra Desktop Assistant
cd /d "C:\Users\chenx\Desktop\LIBRA\LibraAi"

echo Starting Project Libra Desktop GUI...
start "" "C:\Users\chenx\Desktop\LIBRA\LibraAi\venv\Scripts\pythonw.exe" "ui\gui.py"

echo.
echo ======================================================
echo   [Project Libra Desktop Assistant Online]
echo   - Interactive Desktop GUI running on Windows 11
echo   - Public Web Agent: https://smokiness-edition-overhaul.ngrok-free.dev
echo   - Local Web UI: http://localhost:8765
echo ======================================================
ping 127.0.0.1 -n 2 >nul
