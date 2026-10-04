import importlib.util
import subprocess
import sys
from pathlib import Path
from build_checks import verify_frozen_report

root = Path(__file__).resolve().parent
if sys.platform != 'win32':
    raise SystemExit('Phải chạy build EXE trên Windows.')
subprocess.run([sys.executable, 'app.py', '--setup-models'], cwd=root, check=True)
extra_imports = []
if importlib.util.find_spec('scipy._cyutility') is not None:
    extra_imports = ['--hidden-import', 'scipy._cyutility']
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                '--windowed', '--name', 'LV-Studio-Python', '--collect-all', 'easyocr',
                '--collect-all', 'webview', '--hidden-import', 'webview.platforms.winforms',
                '--hidden-import', 'webview.platforms.edgechromium',
                '--add-data', str(root / 'ui') + ';ui',
                '--add-data', str(root / 'models') + ';models', *extra_imports, 'app.py'], cwd=root, check=True)
output = root / 'dist' / 'LV-Studio-Python' / 'LV-Studio-Python.exe'
if not output.is_file():
    raise SystemExit('Không tìm thấy EXE sau khi build.')
report = root / 'kiem-tra-exe.json'
report.unlink(missing_ok=True)
print('Đang chạy thử OCR bằng chính EXE vừa tạo…', flush=True)
result = subprocess.run([str(output), '--self-test', str(report)], cwd=output.parent, timeout=240)
if result.returncode != 0 or not report.is_file():
    if report.is_file():
        print(report.read_text(encoding='utf-8'), flush=True)
    raise SystemExit('EXE chưa chạy được OCR. Xem kiem-tra-exe.json và build-exe.log.')
verified = verify_frozen_report(report)
print('EXE đọc đúng ảnh kiểm tra: AUG LV7. SciPy ' + verified['scipy'], flush=True)
print('Lưu thiết lập đã kiểm tra: API tích hợp trong EXE, không cần launcher phụ.', flush=True)
print('Thiết bị OCR đã kiểm tra: ' + verified.get('device', 'cpu') + ' · ' + verified.get('device_name', 'CPU'), flush=True)
print('BUILD VÀ KIỂM TRA THÀNH CÔNG:', output)
