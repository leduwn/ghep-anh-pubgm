import base64
import io
import json
import re
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_server
from ocr_engine import progress_level, title_level
from PIL import Image


class ParsingTests(unittest.TestCase):
    def test_fraction_mapping(self):
        for text, expected in [('7/7', 7), ('6/7', 6), ('5/8', 5), ('4/8', 4),
                               ('4/5', 4), ('3/5', 3), ('1/3', 1), ('2/3', 2), ('3/3', 4), ('8/8', 8)]:
            with self.subTest(text=text):
                self.assertEqual(progress_level(text)['lv'], expected)

    def test_title_fallback(self):
        for text, expected in [('Cấp 8', 8), ('Cấp G', 6), ('LV 7', 7),
                               ('IV', 4), ('VIII', 8), ('Tên súng - iv', 4)]:
            with self.subTest(text=text):
                self.assertEqual(title_level(text), expected)

    def test_no_weapon_number_as_level(self):
        for text in ['M416', 'M762', 'AKM', '99/99', '8/6', '0/3', 'Cấp 33']:
            self.assertIsNone(title_level(text))
            self.assertIsNone(progress_level(text))


class FakeEngine:
    reader = object()
    state = 'ready'
    error = None
    calls = 0

    logical_size = None

    def recognize(self, image, logical_size=None):
        self.calls += 1
        self.logical_size = logical_size
        assert image.size == ((26, 4) if logical_size else (32, 16))
        return {'lv': 8, 'weapon': 'OTHER', 'confidence': 80}


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = FakeEngine()
        cls.server = create_server(cls.engine, Path(__file__).resolve().parents[1] / 'ui')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        with urlopen(cls.url) as response:
            page = response.read().decode()
        cls.token = json.loads(re.search(r'window.LV_PYTHON=(\{.*?\});', page)[1])['token']
        image = io.BytesIO()
        Image.new('RGB', (32, 16), 'red').save(image, format='PNG')
        cls.body = json.dumps({'image': base64.b64encode(image.getvalue()).decode()}).encode()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, token=None, origin=None):
        headers = {'Content-Type': 'application/json', 'X-LV-Token': token or self.token}
        if origin:
            headers['Origin'] = origin
        return urlopen(Request(self.url + '/api/ocr', self.body, headers))

    def test_local_image_and_unknown_name_keeps_lv(self):
        with self.post(origin=self.url) as response:
            result = json.loads(response.read())
        self.assertEqual(result['lv'], 8)
        self.assertEqual(result['weapon'], 'OTHER')

    def test_invalid_token_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.post(token='wrong')
        self.assertEqual(caught.exception.code, 403)

    def test_other_origin_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.post(origin='https://example.com')
        self.assertEqual(caught.exception.code, 403)

    def test_aachen_asset(self):
        with urlopen(self.url + '/fonts/aachen-bold.otf') as response:
            self.assertGreater(len(response.read()), 1000)

    def test_path_escape_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url + '/%2e%2e/app.py')
        self.assertEqual(caught.exception.code, 404)

    def test_raw_image_upload_and_cache(self):
        output = io.BytesIO()
        Image.new('RGB', (32, 16), 'blue').save(output, format='PNG')
        headers = {'Content-Type': 'image/png', 'X-LV-Token': self.token}
        before = self.engine.calls
        for _ in range(2):
            with urlopen(Request(self.url + '/api/ocr', output.getvalue(), headers)) as response:
                result = json.loads(response.read())
            self.assertEqual(result['lv'], 8)
        self.assertTrue(result['cached'])
        self.assertEqual(result['timings'], {'prepare_ms': 0, 'lv_ms': 0, 'name_ms': 0, 'decode_ms': 0})
        self.assertEqual(self.engine.calls, before + 1)

    def test_compact_ocr_region_keeps_original_coordinate_space(self):
        output = io.BytesIO()
        Image.new('RGB', (26, 4), 'blue').save(output, format='JPEG')
        headers = {'Content-Type': 'image/jpeg', 'X-LV-Token': self.token,
                   'X-LV-Logical-Width': '32', 'X-LV-Logical-Height': '16'}
        with urlopen(Request(self.url + '/api/ocr', output.getvalue(), headers)) as response:
            result = json.loads(response.read())
        self.assertEqual(result['lv'], 8)
        self.assertEqual(self.engine.logical_size, (32, 16))

    def test_invalid_compact_region_rejected(self):
        output = io.BytesIO()
        Image.new('RGB', (8, 2), 'blue').save(output, format='JPEG')
        headers = {'Content-Type': 'image/jpeg', 'X-LV-Token': self.token,
                   'X-LV-Logical-Width': '100', 'X-LV-Logical-Height': '100'}
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.url + '/api/ocr', output.getvalue(), headers))
        self.assertEqual(caught.exception.code, 400)

    def test_failed_engine_does_not_retry_for_every_photo(self):
        before = self.engine.calls
        self.engine.error = 'SciPy missing'
        try:
            for _ in range(3):
                with self.assertRaises(HTTPError) as caught:
                    self.post()
                self.assertEqual(caught.exception.code, 503)
                self.assertTrue(json.loads(caught.exception.read())['engine_unavailable'])
            self.assertEqual(self.engine.calls, before)
        finally:
            self.engine.error = None


if __name__ == '__main__':
    unittest.main()
