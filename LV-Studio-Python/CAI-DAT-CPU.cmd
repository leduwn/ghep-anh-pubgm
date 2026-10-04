@echo off
setlocal
cd /d "%~dp0"
set "LV_TORCH_FLAVOR=cpu"
call CAI-DAT-PYTHON.cmd
exit /b %errorlevel%
