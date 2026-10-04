@echo off
chcp 65001 >nul
title TOOL CẮT ẢNH HÀNH ĐỘNG TỰ ĐỘNG (CHỈ NỀN ĐỎ)
cd /d "%~dp0"

echo =====================================================================
echo   TOOL CẮT ẢNH HÀNH ĐỘNG TỰ ĐỘNG - BALO GAME (CHỈ NỀN ĐỎ)
echo =====================================================================
echo.
echo [*] Đang khởi chạy giao diện...

py -3 cathanhdong.py
if errorlevel 1 (
    python cathanhdong.py
)

if errorlevel 1 (
    echo.
    echo [X] Lỗi: Không thể khởi động cathanhdong.py!
    echo [*] Vui lòng kiểm tra Python và các thư viện cần thiết.
    echo.
    pause
)
