@echo off
chcp 65001 >nul
cd /d "%~dp0"
py catmatna.py
if errorlevel 1 (
    echo.
    echo [Lỗi] Không thể khởi động catmatna.py.
    pause
)
