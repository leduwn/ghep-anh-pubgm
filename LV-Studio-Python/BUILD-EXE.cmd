@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
if not exist "installation-ok.json" goto missing
if not exist ".venv\Scripts\python.exe" goto missing
echo Dang build EXE. Lan dau co the mat vai phut, vui long giu cua so nay.
echo Chi tiet dang duoc ghi vao build-exe.log trong thu muc app.
".venv\Scripts\python.exe" build_exe.py >build-exe.log 2>&1
if errorlevel 1 goto failed
if not exist "dist\LV-Studio-Python\LV-Studio-Python.exe" goto failed
echo.
echo BUILD VA KIEM TRA OCR THANH CONG.
echo File: dist\LV-Studio-Python\LV-Studio-Python.exe
echo Giu ca thu muc LV-Studio-Python, bao gom thu muc _internal.
start "" explorer.exe "%CD%\dist\LV-Studio-Python"
pause
exit /b 0
:missing
echo Bam CAI-DAT-PYTHON.cmd truoc, sau do build lai.
pause
exit /b 1
:failed
echo.
echo BUILD HOAC KIEM TRA OCR THAT BAI. Gui build-exe.log va kiem-tra-exe.json (neu co).
type build-exe.log
pause
exit /b 1
