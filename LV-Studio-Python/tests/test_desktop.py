import base64
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_support import DesktopApi, dib_bytes, ensure_stdio, png_bytes


class ExportTests(unittest.TestCase):
    def setUp(self):
        image = Image.new('RGB', (17, 11), (40, 100, 220))
        output = io.BytesIO()
        image.save(output, 'PNG')
        self.data = output.getvalue()
        self.encoded = base64.b64encode(self.data).decode()

    def test_clipboard_dib_keeps_image_size_and_color(self):
        from PIL import BmpImagePlugin
        with BmpImagePlugin.DibImageFile(io.BytesIO(dib_bytes(self.data))) as image:
            self.assertEqual(image.size, (17, 11))
            self.assertEqual(image.getpixel((4, 4)), (40, 100, 220))

    def test_invalid_png_rejected(self):
        with self.assertRaises(ValueError):
            png_bytes(base64.b64encode(b'not a png').decode())

    @patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(SAVE=1))})
    def test_save_dialog_exports_exact_png_bytes(self):
        with tempfile.TemporaryDirectory() as location:
            destination = Path(location) / 'ảnh ghép.png'
            api = DesktopApi(Path(location) / 'app.log')
            api._window = type('Window', (), {'create_file_dialog': lambda *args, **kwargs: [str(destination)]})()
            result = api.save_png(self.encoded, 'LV-Studio.png')
            self.assertTrue(result['saved'])
            self.assertEqual(destination.read_bytes(), self.data)

    @patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(SAVE=1))})
    def test_cancel_save_does_not_write_image(self):
        api = DesktopApi('app.log')
        api._window = type('Window', (), {'create_file_dialog': lambda *args, **kwargs: None})()
        self.assertEqual(api.save_png(self.encoded, 'LV-Studio.png'), {'cancelled': True})

    def test_missing_console_streams_are_usable(self):
        with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
            ensure_stdio()
            sys.stdout.write('stdout available')
            sys.stderr.write('stderr available')
            sys.stdout.close()
            sys.stderr.close()


if __name__ == '__main__':
    unittest.main()
