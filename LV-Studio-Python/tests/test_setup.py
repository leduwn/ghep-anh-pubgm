import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from setup_environment import verify_ready


class SetupVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.python = self.root / 'python.exe'
        self.python.write_bytes(b'test fixture')
        models = self.root / 'models'
        models.mkdir()
        for name in ('craft_mlt_25k.pth', 'latin_g2.pth'):
            (models / name).write_bytes(b'test fixture')

    def test_zero_exit_without_running_python_is_not_success(self):
        response = subprocess.CompletedProcess([], 0, '', '[ERROR] No runtime installed that matches 3.11')
        with patch('setup_environment.subprocess.run', return_value=response):
            with self.assertRaises(RuntimeError):
                verify_ready(self.python, self.root)

    def test_import_error_is_not_success(self):
        response = subprocess.CompletedProcess([], 1, '', 'ModuleNotFoundError: easyocr')
        with patch('setup_environment.subprocess.run', return_value=response):
            with self.assertRaises(RuntimeError):
                verify_ready(self.python, self.root)

    def test_missing_model_is_not_success(self):
        (self.root / 'models' / 'latin_g2.pth').unlink()
        with self.assertRaises(RuntimeError):
            verify_ready(self.python, self.root)

    def test_only_confirmed_execution_is_success(self):
        response = subprocess.CompletedProcess([], 0, 'LV_SETUP_READY\n', '')
        with patch('setup_environment.subprocess.run', return_value=response):
            verify_ready(self.python, self.root)


if __name__ == '__main__':
    unittest.main()
