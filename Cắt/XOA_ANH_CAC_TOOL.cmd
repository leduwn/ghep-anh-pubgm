@echo off
chcp 65001 >nul
title DỌN DẸP INPUT/OUTPUT TẠM CÁC TOOL CẮT

echo =====================================================================
echo           DỌN DẸP INPUT/OUTPUT TẠM CỦA TỪNG TOOL CON
echo   (Giữ nguyên 100%% ảnh gốc trong input/ và ảnh đã cắt trong output/)
echo =====================================================================
echo.

python "%~dp0clean_tools.py"

echo.
pause
