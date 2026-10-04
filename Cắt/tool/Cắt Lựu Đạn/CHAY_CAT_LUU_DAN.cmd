@echo off
chcp 65001 >nul
title TOOL CẮT ẢNH LỰU ĐẠN TỰ ĐỘNG (CHỈ NỀN ĐỎ & TÍM)
cd /d "%~dp0"

echo =====================================================================
echo   TOOL CẮT ẢNH LỰU ĐẠN TỰ ĐỘNG - BALO GAME (NỀN ĐỎ & TÍM)
echo =====================================================================
echo.
echo [*] Đang khởi chạy giao diện...

py -3 catluudan.py
if errorlevel 1 (
    python catluudan.py
)

if errorlevel 1 (
    echo.
    echo [X] Lỗi: Không thể khởi động catluudan.py!
    echo [*] Vui lòng kiểm tra Python và các thư viện cần thiết.
    echo.
    pause
)
