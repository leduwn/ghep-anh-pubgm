import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_checks import verify_frozen_report


class BuildChecksTests(unittest.TestCase):
    def test_rejects_failed_ocr_or_source_only_test(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            for report in [
                {'ok': False, 'frozen': True, 'error': 'No module named scipy._cyutility'},
                {'ok': True, 'frozen': False, 'result': {'lv': 7, 'weapon': 'AUG'}},
                {'ok': True, 'frozen': True, 'result': {'lv': None, 'weapon': 'AUG'}},
                {'ok': True, 'frozen': True, 'result': {'lv': 7, 'weapon': 'AUG'}},
            ]:
                path.write_text(json.dumps(report))
                with self.assertRaises(RuntimeError):
                    verify_frozen_report(path)

    def test_accepts_verified_packaged_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            report = {'ok': True, 'frozen': True, 'settings_api': True, 'result': {'lv': 7, 'weapon': 'AUG'}}
            path.write_text(json.dumps(report))
            self.assertTrue(verify_frozen_report(path)['ok'])


if __name__ == '__main__':
    unittest.main()
