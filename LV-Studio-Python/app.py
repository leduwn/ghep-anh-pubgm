import argparse
import base64
import io
import json
import logging
import mimetypes
import os
import secrets
import shutil
import sys
import threading
import time
import hashlib
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ocr_engine import LevelEngine
from desktop_support import ensure_stdio, open_desktop, DesktopApi

ensure_stdio()

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def setup_models():
    destination = ROOT / 'models'
    destination.mkdir(exist_ok=True)
    cache = Path.home() / '.EasyOCR' / 'model'
    for name in ('craft_mlt_25k.pth', 'latin_g2.pth'):
        if not (destination / name).exists() and (cache / name).is_file():
            print('Dùng model sẵn có:', name, flush=True)
            shutil.copy2(cache / name, destination / name)
    print('Đang kiểm tra/tải model EasyOCR vi/en. Lần đầu có thể mất vài phút.', flush=True)
    engine = LevelEngine(destination)
    engine.warm(download=True)
    print(engine.state, flush=True)
    print('Model EasyOCR đã sẵn sàng.', flush=True)


def create_server(engine, ui_dir, desktop_api=None):
    token = secrets.token_urlsafe(32)
    ui_dir = Path(ui_dir).resolve()
    cache = OrderedDict()
    cache_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.info(fmt, *args)

        def send_json(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            target = unquote(urlsplit(self.path).path)
            if target.startswith('/api/import-image/'):
                if not secrets.compare_digest(self.headers.get('X-LV-Token', ''), token):
                    self.send_error(403)
                    return
                try:
                    if desktop_api is None:
                        raise ValueError('No desktop import')
                    data, mime = desktop_api.read_acc_bytes(target.removeprefix('/api/import-image/'))
                except (ValueError, OSError):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
                return
            if target == '/api/status':
                self.send_json(200, {'ready': engine.reader is not None, 'status': engine.state, 'error': engine.error,
                                     'device': getattr(engine, 'device', 'cpu'),
                                     'device_name': getattr(engine, 'device_name', 'CPU'),
                                     'device_note': getattr(engine, 'device_note', '')})
                return
            file = (ui_dir / (target.lstrip('/') or 'index.html')).resolve()
            if not file.is_relative_to(ui_dir) or not file.is_file():
                self.send_error(404)
                return
            data = file.read_bytes()
            if file.name == 'index.html':
                config = '<script>window.LV_PYTHON=' + json.dumps({'token': token}) + ';</script>'
                data = data.replace(b'</head>', config.encode() + b'</head>')
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            route = urlsplit(self.path).path
            if route not in {'/api/ocr', '/api/uid', '/api/misc'}:
                self.send_error(404)
                return
            if self.headers.get('X-LV-Token') != token:
                self.send_json(403, {'error': 'Phiên ứng dụng không hợp lệ. Hãy mở lại giao diện.'})
                return
            origin = self.headers.get('Origin')
            if origin and origin != f'http://127.0.0.1:{self.server.server_port}':
                self.send_json(403, {'error': 'Nguồn yêu cầu không hợp lệ.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 40 * 1024 * 1024:
                    self.send_json(413, {'error': 'Ảnh quá lớn để nhận diện.'})
                    return
                if engine.error and route != '/api/misc':
                    self.send_json(503, {'error': engine.error, 'engine_unavailable': True})
                    return
                body = self.rfile.read(length)
                if self.headers.get('Content-Type', '').split(';')[0] == 'application/json':
                    payload = json.loads(body)
                    image_data = base64.b64decode(payload['image'], validate=True)
                else:
                    image_data = body
                logical_width = int(self.headers.get('X-LV-Logical-Width', '0') or 0)
                logical_height = int(self.headers.get('X-LV-Logical-Height', '0') or 0)
                key = hashlib.sha256(image_data)
                uid_cropped = self.headers.get('X-LV-UID-Crop') == '1'
                key.update(f'{route}:{logical_width}x{logical_height}:{uid_cropped}'.encode())
                cache_key = key.digest()
                force = self.headers.get('X-LV-Force') == '1'
                with cache_lock:
                    cached = cache.get(cache_key)
                    if cached is not None:
                        cache.move_to_end(cache_key)
                if cached is not None and not force:
                    self.send_json(200, {**cached, 'cached': True, 'timings': {'prepare_ms': 0, 'lv_ms': 0, 'name_ms': 0, 'decode_ms': 0}})
                    return
                decode_started = time.perf_counter()
                from PIL import Image, ImageOps
                with Image.open(io.BytesIO(image_data)) as image:
                    image = ImageOps.exif_transpose(image).convert('RGB')
                    logical_size = None
                    if logical_width and logical_height:
                        valid_crop = (image.width <= logical_width <= 10000 and
                                      image.height <= logical_height <= 10000 and
                                      image.width >= logical_width * .75 and
                                      image.height >= logical_height * .18)
                        if not valid_crop:
                            self.send_json(400, {'error': 'Kích thước vùng OCR không hợp lệ.'})
                            return
                        logical_size = (logical_width, logical_height)
                    decode_ms = (time.perf_counter() - decode_started) * 1000
                    if route == '/api/misc':
                        from misc_detector import detect_misc
                        result = detect_misc(image)
                    elif route == '/api/uid':
                        result = engine.recognize_uid(image, cropped=True) if uid_cropped else engine.recognize_uid(image)
                    else:
                        result = engine.recognize(image, logical_size=logical_size)
                    result.setdefault('timings', {})['decode_ms'] = round(decode_ms, 2)
                if (result.get('lv') and result.get('name_known', True)) or result.get('uid'):
                    with cache_lock:
                        cache[cache_key] = result
                        while len(cache) > 512:
                            cache.popitem(last=False)
                self.send_json(200, result)
            except Exception as exc:
                logging.exception('OCR failed')
                self.send_json(500, {'error': 'EasyOCR gặp lỗi: ' + str(exc),
                                     'engine_unavailable': bool(engine.error)})

    return ThreadingHTTPServer(('127.0.0.1', 0), Handler)


def run_app(headless=False):
    log_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LV-Studio-Python'
    log_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_root / 'app.log', level=logging.INFO, encoding='utf-8')
    logging.info('LV Studio Desktop 1.4.4; frozen=%s; resources=%s', getattr(sys, 'frozen', False), ROOT)
    engine = LevelEngine(ROOT / 'models')
    api = DesktopApi(log_root / 'app.log')
    api._binary_import = True
    server = create_server(engine, ROOT / 'ui', api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    def warm():
        try:
            engine.warm(download=False)
        except Exception:
            logging.exception('EasyOCR initialization failed')
    threading.Thread(target=warm, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    if headless:
        print(url, flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            server.shutdown()
        return
    try:
        open_desktop(url, log_root / 'app.log', engine, api)
    except Exception as exc:
        logging.exception('Desktop initialization failed')
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'Chưa mở được cửa sổ LV Studio:\n' + str(exc) +
                '\n\nChi tiết: ' + str(log_root / 'app.log'), 'LV Studio', 0x10)
        raise
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument('--setup-models', action='store_true')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--self-test', type=Path, metavar='REPORT_JSON')
    args = parser.parse_args()
    if args.self_test:
        from build_checks import run_ocr_self_test
        sys.exit(0 if run_ocr_self_test(ROOT, args.self_test) else 1)
    elif args.setup_models:
        setup_models()
    else:
        run_app(args.headless)
