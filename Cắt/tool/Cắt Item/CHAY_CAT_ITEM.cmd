@echo off
chcp 65001 >nul
title TOOL CẮT ẢNH ITEM / VẬT PHẨM TỰ ĐỘNG (LƯỚI 3 CỘT 216x216)
cd /d "%~dp0"

echo =====================================================================
echo   TOOL CẮT ẢNH ITEM / VẬT PHẨM TỰ ĐỘNG - KHO ĐỒ PUBG MOBILE
echo =====================================================================
echo.
echo [*] Đang khởi chạy giao diện...

py -3 catitem.py
if errorlevel 1 (
    python catitem.py
)

if errorlevel 1 (
    echo.
    echo [X] Lỗi: Không thể khởi động catitem.py!
    echo [*] Vui lòng kiểm tra Python và các thư viện cần thiết.
    echo.
    pause
)
