@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
if not exist "installation-ok.json" goto missing
if not exist ".venv\Scripts\python.exe" goto missing
if not exist "models\craft_mlt_25k.pth" goto missing
if not exist "models\latin_g2.pth" goto missing
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
  echo.
  echo App chua khoi dong duoc. Xem loi ben tren.
  pause
  exit /b 1
)
exit /b 0
:missing
echo Bam CAI-DAT-PYTHON.cmd truoc, sau do chay lai file nay.
pause
exit /b 1
