@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=0"
set "LV_PY="
echo LV Studio Desktop 1.4.4 - cai dat Python va EasyOCR
echo Lan dau can Internet de tai thu vien va model.
call :probe py -3.11
if defined LV_PY goto install
call :probe py -3.12
if defined LV_PY goto install
call :probe py -3.10
if defined LV_PY goto install
call :probe python
if defined LV_PY goto install
echo.
echo Chua tim thay Python 3.10-3.12 ban 64-bit.
echo Dang thu cai Python 3.11 bang Python Install Manager...
py install 3.11 >python-runtime.log 2>&1
type python-runtime.log
call :probe py -3.11
if defined LV_PY goto install
echo.
echo Chua cai duoc Python phu hop. KHONG the chay app luc nay.
echo Gui file python-runtime.log de kiem tra.
echo Hoac cai Python 3.11 64-bit tu python.org roi bam lai file nay.
pause
exit /b 1

:install
echo.
echo Da xac nhan Python: %LV_PY%
if exist "installation-ok.json" del /q "installation-ok.json"
if exist "installation-ok.json" goto failed
%LV_PY% setup_environment.py
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" goto failed
if not exist "models\craft_mlt_25k.pth" goto failed
if not exist "models\latin_g2.pth" goto failed
if not exist "installation-ok.json" goto failed
echo.
echo CAI DAT THANH CONG. Bam CHAY-APP.cmd de su dung.
pause
exit /b 0

:failed
echo.
echo CAI DAT CHUA THANH CONG. Khong chay CHAY-APP.cmd luc nay.
echo Gui cai-dat.log va python-probe.log de kiem tra.
pause
exit /b 1

:probe
%* -c "import struct,sys;print('LV_PYTHON_READY' if (3,10)<=sys.version_info[:2]<=(3,12) and struct.calcsize('P')==8 else 'LV_PYTHON_UNSUPPORTED')" >python-probe.log 2>&1
findstr /x /c:"LV_PYTHON_READY" python-probe.log >nul 2>&1
if errorlevel 1 exit /b 1
set "LV_PY=%*"
exit /b 0
