@echo off
chcp 65001 >nul
cd /d "%~dp0"
python catsung.py
if errorlevel 1 (
    echo.
    echo [Lỗi] Không thể khởi động catsung.py.
    pause
)
