"""Desktop window, image export and Windows clipboard support."""
import base64
import io
import json
import tempfile
import os
import sys
import mimetypes
import secrets
from pathlib import Path

WINDOW_TITLE = 'LV Studio · Trọng 2k8'


def ensure_stdio():
    # Windowed PyInstaller executables do not have console streams.
    for name in ('stdout', 'stderr'):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, 'w', encoding='utf-8'))


def png_bytes(encoded):
    if not isinstance(encoded, str) or len(encoded) > 110 * 1024 * 1024:
        raise ValueError('Ảnh xuất quá lớn.')
    data = base64.b64decode(encoded, validate=True)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Ảnh xuất không phải PNG.')
    return data


def dib_bytes(data):
    from PIL import Image
    output = io.BytesIO()
    with Image.open(io.BytesIO(data)) as image:
        image.convert('RGB').save(output, 'BMP')
    return output.getvalue()[14:]


def copy_windows_image(data):
    if sys.platform != 'win32':
        raise RuntimeError('Copy ảnh desktop hiện hỗ trợ Windows.')
    import ctypes
    import time
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.GetForegroundWindow.restype = wintypes.HWND
    user.OpenClipboard.argtypes = [wintypes.HWND]
    user.OpenClipboard.restype = wintypes.BOOL
    user.EmptyClipboard.restype = wintypes.BOOL
    user.CloseClipboard.restype = wintypes.BOOL
    user.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user.RegisterClipboardFormatW.restype = wintypes.UINT
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HANDLE
    kernel.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel.GlobalFree.restype = wintypes.HANDLE
    owner = user.FindWindowW(None, WINDOW_TITLE) or user.GetForegroundWindow()
    if not owner:
        raise RuntimeError('Chưa tìm thấy cửa sổ để copy ảnh.')
    formats = [(8, dib_bytes(data))]  # CF_DIB: paste as an image in Photoshop.
    png_format = user.RegisterClipboardFormatW('PNG')
    if png_format:
        formats.append((png_format, data))
    for _ in range(20):
        if user.OpenClipboard(owner):
            break
        time.sleep(.025)
    else:
        raise RuntimeError('Clipboard đang bận. Hãy bấm Copy ảnh lại.')
    try:
        if not user.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        for format_id, payload in formats:
            handle = kernel.GlobalAlloc(0x42, len(payload))
            if not handle:
                raise MemoryError('Không đủ bộ nhớ để copy ảnh.')
            transferred = False
            try:
                pointer = kernel.GlobalLock(handle)
                if not pointer:
                    raise ctypes.WinError(ctypes.get_last_error())
                ctypes.memmove(pointer, payload, len(payload))
                kernel.GlobalUnlock(handle)
                if not user.SetClipboardData(format_id, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                transferred = True  # Clipboard now owns the allocation.
            finally:
                if not transferred:
                    kernel.GlobalFree(handle)
    finally:
        user.CloseClipboard()


class DesktopApi:
    def __init__(self, log_file):
        self._window = None
        self._log_file = Path(log_file)
        self._import_files = {}
        self._import_root = None

    def _settings_path(self):
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LV-Studio-Python' / 'settings.json'

    def load_settings(self):
        path = self._settings_path()
        if not path.exists():
            return {'settings': None}
        if path.stat().st_size > 65536:
            raise ValueError('File thiết lập quá lớn.')
        return {'settings': json.loads(path.read_text(encoding='utf-8-sig'))}

    def save_settings(self, settings):
        if not isinstance(settings, dict) or settings.get('version') != 1:
            raise ValueError('Thiết lập không hợp lệ.')
        payload = json.dumps(settings, ensure_ascii=False).encode('utf-8')
        if len(payload) > 65536:
            raise ValueError('Thiết lập quá lớn.')
        path = self._settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='settings-', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return {'saved': True}

    def read_misc(self, encoded):
        from PIL import Image
        from misc_detector import detect_misc
        with Image.open(io.BytesIO(png_bytes(encoded))) as image:
            return detect_misc(image)

    def read_uid(self, encoded, cropped=False):
        if getattr(self, '_engine', None) is None:
            raise RuntimeError('Chưa nối được bộ đọc UID. Mở EXE mới đã build từ bản 16.')
        from PIL import Image
        with Image.open(io.BytesIO(png_bytes(encoded))) as image:
            return self._engine.recognize_uid(image.convert('RGB'), cropped=True) if cropped else self._engine.recognize_uid(image.convert('RGB'))

    def choose_acc_folder(self):
        import webview
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not selected:
            return {'cancelled': True}
        root = Path(selected[0]).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Hãy chọn một thư mục acc.')
        manifest, granted = [], {}
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'} or not path.is_file():
                continue
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            stat = resolved.stat()
            if stat.st_size > 20 * 1024 * 1024:
                raise ValueError('Ảnh ' + path.name + ' vượt 20 MB.')
            key = secrets.token_urlsafe(18)
            granted[key] = resolved
            manifest.append({'id': key, 'name': path.name,
                             'relativePath': root.name + '/' + path.relative_to(root).as_posix(),
                             'lastModified': int(stat.st_mtime * 1000)})
        self._import_root = root
        self._import_files = granted
        return {'files': manifest, 'binary': getattr(self, '_binary_import', False)}

    def read_acc_bytes(self, file_id):
        path = self._import_files.get(file_id)
        if path is None or self._import_root is None:
            raise ValueError('Ảnh chưa được chọn qua hộp thư mục.')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self._import_root):
            raise ValueError('Ảnh nằm ngoài thư mục đã chọn.')
        with resolved.open('rb') as stream:
            data = stream.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError('Ảnh vượt 20 MB.')
        return data, mimetypes.guess_type(resolved.name)[0] or 'image/png'

    def read_acc_image(self, file_id):
        data, mime = self.read_acc_bytes(file_id)
        return {'base64': base64.b64encode(data).decode('ascii'),
                'mime': mime}

    def save_png(self, encoded, filename):
        import webview
        data = png_bytes(encoded)
        selected = self._window.create_file_dialog(webview.FileDialog.SAVE,
                    save_filename=Path(filename).name, file_types=('PNG (*.png)',))
        if not selected:
            return {'cancelled': True}
        destination = Path(selected[0])
        if destination.suffix.lower() != '.png':
            destination = destination.with_suffix('.png')
        destination.write_bytes(data)
        return {'saved': True, 'name': destination.name}

    def copy_png(self, encoded):
        copy_windows_image(png_bytes(encoded))
        return {'copied': True}

    def save_log(self):
        import logging
        import webview
        for handler in logging.getLogger().handlers:
            handler.flush()
        selected = self._window.create_file_dialog(webview.FileDialog.SAVE,
                    save_filename='LV-Studio-app.log', file_types=('Log (*.log)',))
        if not selected:
            return {'cancelled': True}
        Path(selected[0]).write_bytes(self._log_file.read_bytes())
        return {'saved': True}


def open_desktop(url, log_file, engine=None, api=None):
    import webview
    if sys.platform == 'win32':
        from webview.platforms import winforms
        if not winforms.is_chromium:
            raise RuntimeError('Cần Microsoft Edge WebView2 Runtime để mở giao diện LV Studio.')
    api = api or DesktopApi(log_file)
    api._engine = engine
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window(WINDOW_TITLE, url, js_api=api, width=1280, height=860,
                                   min_size=(900, 620), background_color='#0b0e13')
    api._window = window
    webview.start(gui='edgechromium', debug=False)
