@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo LV Studio - EXE tich hop luu thiet lap
echo Day la buoc tao EXE mot lan. Khi dung app hang ngay chi mo EXE.
if not exist ".venv\Scripts\python.exe" goto setup
if not exist "installation-ok.json" goto setup
goto build
:setup
echo Chuan bi Python va thu vien. Lan dau can Internet.
call CAI-DAT-PYTHON.cmd
if errorlevel 1 exit /b 1
:build
call BUILD-EXE.cmd
exit /b %errorlevel%
