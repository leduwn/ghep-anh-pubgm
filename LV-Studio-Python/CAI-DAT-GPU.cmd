@echo off
setlocal
cd /d "%~dp0"
set "LV_TORCH_FLAVOR=cu128"
call CAI-DAT-PYTHON.cmd
exit /b %errorlevel%
