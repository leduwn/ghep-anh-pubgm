import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_support import DesktopApi

class FolderImportTests(unittest.TestCase):
    def api(self, selection):
        api = DesktopApi('test.log')
        api._window = SimpleNamespace(create_file_dialog=lambda *args, **kwargs: selection)
        return api

    def test_cancel_and_unknown_file_id(self):
        api = self.api(None)
        with patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=3))}):
            self.assertEqual(api.choose_acc_folder(), {'cancelled': True})
        with self.assertRaises(ValueError): api.read_acc_image('/etc/passwd')

    def test_manifest_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'acc'
            image = root / 'Ảnh nền' / 'gốc.PNG'
            image.parent.mkdir(parents=True)
            image.write_bytes(b'original-image-bytes')
            (root / 'ignored.txt').write_text('skip')
            api = self.api([str(root)])
            with patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=3))}):
                result = api.choose_acc_folder()
            self.assertEqual(len(result['files']), 1)
            meta = result['files'][0]
            self.assertEqual(meta['relativePath'], 'acc/Ảnh nền/gốc.PNG')
            payload = api.read_acc_image(meta['id'])
            self.assertEqual(base64.b64decode(payload['base64']), image.read_bytes())
            self.assertEqual(payload['mime'], 'image/png')
            self.assertEqual(meta['lastModified'], int(image.stat().st_mtime * 1000))

    def test_outside_symlink_not_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'acc'; root.mkdir()
            outside = Path(tmp) / 'outside.png'; outside.write_bytes(b'outside')
            (root / 'link.png').symlink_to(outside)
            api = self.api([str(root)])
            with patch.dict(sys.modules, {'webview': SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=3))}):
                self.assertEqual(api.choose_acc_folder()['files'], [])
