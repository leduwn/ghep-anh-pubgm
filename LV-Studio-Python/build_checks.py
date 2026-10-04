"""Run the actual packaged OCR before declaring the Windows build usable."""
import json
import os
import sys
import time
import tempfile
import traceback
from pathlib import Path


def run_ocr_self_test(root, report_path):
    started = time.perf_counter()
    report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False))}
    try:
        # Test persistence through the same native API bundled into this EXE.
        # Use a disposable directory so building never changes the user's settings.
        from desktop_support import DesktopApi
        with tempfile.TemporaryDirectory() as folder:
            api = DesktopApi(Path(folder) / 'test.log')
            settings_file = Path(folder) / 'settings.json'
            api._settings_path = lambda: settings_file
            first = {'version': 1, 'controls': {'bgHeight': '85'}, 'rects': {}}
            api.save_settings(first)
            reopened = DesktopApi(Path(folder) / 'test.log')
            reopened._settings_path = lambda: settings_file
            if reopened.load_settings()['settings'] != first:
                raise RuntimeError('EXE không khôi phục được thiết lập đã lưu.')
            first['controls']['bgHeight'] = '115'
            reopened.save_settings(first)
            if api.load_settings()['settings'] != first:
                raise RuntimeError('EXE không thay thế được thiết lập khi lưu lần tiếp theo.')
        report['settings_api'] = True
        import scipy
        import torch
        import scipy.ndimage
        from scipy._lib._ccallback import LowLevelCallable
        from PIL import Image, ImageDraw
        import io, base64
        probe=Image.new('RGB',(600,400),(180,180,180))
        draw=ImageDraw.Draw(probe)
        for row in range(2):
            for col in range(3):
                x,y=50+col*130,50+row*130
                draw.rectangle((x,y,x+119,y+119),fill=(90,20,40))
                draw.ellipse((x+35,y+20,x+85,y+100),fill='white')
        encoded=io.BytesIO();probe.save(encoded,'PNG')
        tiles=api.read_misc(base64.b64encode(encoded.getvalue()).decode())
        if len(tiles['rects']) != 6 or tiles['locked']:
            raise RuntimeError('EXE chưa tự cắt được 6 ô Linh tinh.')
        report['misc_api'] = True
        from ocr_engine import LevelEngine
        engine = LevelEngine(Path(root) / 'models')
        engine.warm(download=False)
        with Image.open(Path(root) / 'ui' / 'sample.jpg') as image:
            result = engine.recognize(image)
        report.update(scipy=scipy.__version__, result=result, device=engine.device, device_name=engine.device_name,
                      torch=torch.__version__, cuda_runtime=torch.version.cuda)
        if result.get('lv') != 7 or result.get('weapon') != 'AUG':
            raise RuntimeError('Ảnh kiểm tra phải là AUG LV7; kết quả: ' + str(result))
        # CUDA builds must also work on a recipient's CPU-only machine.
        if engine.device == 'cuda':
            engine._use_cpu('Kiểm tra CPU trong bản build')
            with Image.open(Path(root) / 'ui' / 'sample.jpg') as image:
                cpu_result = engine.recognize(image)
            report['cpu_result'] = cpu_result
            if cpu_result.get('lv') != 7 or cpu_result.get('weapon') != 'AUG':
                raise RuntimeError('Kiểm tra CPU dự phòng chưa đọc đúng AUG LV7.')
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    report['seconds'] = round(time.perf_counter() - started, 2)
    target = Path(report_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, target)
    return report['ok']


def verify_frozen_report(path):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if not report.get('ok') or not report.get('frozen'):
        raise RuntimeError('EXE chưa vượt qua kiểm tra OCR:\n' + report.get('error', str(report)))
    if report.get('result', {}).get('lv') != 7 or report.get('result', {}).get('weapon') != 'AUG':
        raise RuntimeError('Kết quả kiểm tra OCR trong EXE không đúng.')
    if report.get('settings_api') is not True:
        raise RuntimeError('EXE chưa vượt qua kiểm tra lưu thiết lập tích hợp.')
    return report
