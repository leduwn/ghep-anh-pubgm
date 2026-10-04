"""Install into a private venv; keep the complete output in cai-dat.log."""
import os
import json
import struct
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify_ready(python, root):
    """Do not accept a launcher's zero exit code as proof Python executed."""
    if not python.is_file():
        raise RuntimeError('Chưa tạo được Python trong .venv.')
    for filename in ('craft_mlt_25k.pth', 'latin_g2.pth'):
        if not (root / 'models' / filename).is_file():
            raise RuntimeError('Chưa có model: ' + filename)
    command = [str(python), '-c',
               "import torch,torchvision,easyocr,cv2,numpy,PIL,webview,PyInstaller;"
               "from ocr_engine import LevelEngine;"
               "LevelEngine('models').warm(download=False);print('LV_SETUP_READY')"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if result.returncode != 0 or 'LV_SETUP_READY' not in result.stdout.splitlines():
        raise RuntimeError('Kiểm tra môi trường OCR thất bại:\n' + result.stdout + result.stderr)


def torch_flavor():
    """Select CUDA wheels when a driver is visible; explicit override for sharing."""
    preferred = os.environ.get('LV_TORCH_FLAVOR', 'auto').lower()
    if preferred in ('cpu', 'cu128'):
        return preferred
    candidates = ['nvidia-smi', str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe'),
                  str(Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'NVIDIA Corporation' / 'NVSMI' / 'nvidia-smi.exe')]
    for executable in candidates:
        try:
            result = subprocess.run([executable, '--query-gpu=name', '--format=csv,noheader'],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return 'cu128'
        except (OSError, subprocess.TimeoutExpired):
            pass
    return 'cpu'


def torch_install_command(python, flavor):
    versions = ('torch==2.7.1+cu128', 'torchvision==0.22.1+cu128') if flavor == 'cu128' else (
        'torch==2.5.1+cpu', 'torchvision==0.20.1+cpu')
    return [str(python), '-m', 'pip', 'install', *versions, '--index-url',
            'https://download.pytorch.org/whl/' + flavor]


def main():
    completed = ROOT / 'installation-ok.json'
    completed.unlink(missing_ok=True)
    if sys.platform != 'win32':
        raise RuntimeError('Bộ cài này dành cho Windows.')
    if not (3, 10) <= sys.version_info[:2] <= (3, 12) or struct.calcsize('P') != 8:
        raise RuntimeError('Cần Python 3.10–3.12 bản 64-bit. Khuyên dùng Python 3.11.')
    env = dict(os.environ, PYTHONUTF8='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    directory = ROOT / '.venv'
    print('Tạo môi trường Python riêng trong .venv…', flush=True)
    venv.EnvBuilder(with_pip=True).create(directory)
    python = directory / 'Scripts' / 'python.exe'
    flavor = torch_flavor()
    print('Bộ thư viện được chọn: ' + ('NVIDIA CUDA 12.8 (tải lớn hơn CPU)' if flavor == 'cu128' else 'CPU'), flush=True)
    steps = [
        ('Cập nhật pip', [str(python), '-m', 'pip', 'install', '--upgrade', 'pip']),
        ('Cài PyTorch ' + flavor, torch_install_command(python, flavor)),
        ('Cài EasyOCR và công cụ đóng gói', [str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')]),
        ('Kiểm tra xung đột thư viện', [str(python), '-m', 'pip', 'check']),
        ('Kiểm tra model OCR', [str(python), str(ROOT / 'app.py'), '--setup-models']),
    ]
    with (ROOT / 'cai-dat.log').open('w', encoding='utf-8') as log:
        log.write(f'Python: {sys.version}\nExecutable: {sys.executable}\n')
        for label, command in steps:
            print('\n' + label + '…', flush=True)
            log.write('\n' + label + '\n')
            log.flush()
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for line in process.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            if process.wait() != 0:
                raise RuntimeError(label + ' thất bại. Xem cai-dat.log trong thư mục app.')
        print('\nXác minh Python, thư viện và model đã chạy được…', flush=True)
        try:
            verify_ready(python, ROOT)
        except Exception as exc:
            log.write('\nXác minh thất bại: ' + str(exc) + '\n')
            raise
    temporary = completed.with_suffix('.tmp')
    temporary.write_text(json.dumps({'ready': True, 'python': str(python),
                                     'version': sys.version, 'app': '1.4.4', 'torch_flavor': flavor}), encoding='utf-8')
    temporary.replace(completed)
    print('\nCÀI ĐẶT THÀNH CÔNG. Bấm CHAY-APP.cmd để thử.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('\nCÀI ĐẶT CHƯA THÀNH CÔNG:', exc, file=sys.stderr, flush=True)
        sys.exit(1)
