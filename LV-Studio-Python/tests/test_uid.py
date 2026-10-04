import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import threading
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ocr_engine import uid_from_results, LevelEngine

def item(text, x=0, y=0, confidence=.99):
    return ([[x,y],[x+30,y],[x+30,y+12],[x,y+12]],text,confidence)

class UidTests(unittest.TestCase):
    def test_combined_uid_preserves_digits(self):
        self.assertEqual(uid_from_results([item('UID: 51206386631')])[0], '51206386631')
        self.assertEqual(uid_from_results([item('UID: 00123456789')])[0], '00123456789')

    def test_unrelated_numbers_rejected(self):
        self.assertIsNone(uid_from_results([item('51206386631'),item('Cấp 68')])[0])
        self.assertIsNone(uid_from_results([item('UID: 68')])[0])

    def test_split_same_line_only(self):
        self.assertEqual(uid_from_results([item('UID:'),item('51206386631',x=35)])[0], '51206386631')
        self.assertIsNone(uid_from_results([item('UID:'),item('51206386631',x=35,y=200)])[0])

    def test_recognition_crops_profile_region(self):
        engine=LevelEngine('unused');engine.warm=lambda **kwargs:None
        calls=[]
        def read(pixels,**kwargs):
            calls.append((pixels.shape,kwargs));return [item('UID:51206386631')]
        engine._readtext=read
        result=engine.recognize_uid(Image.new('RGB',(2000,1400)))
        self.assertEqual(result['uid'],'51206386631')
        self.assertEqual(calls[0][0],(266,720,3))
        self.assertIn('UID', calls[0][1]['allowlist'])

class UidEndpointTests(unittest.TestCase):
    def test_authenticated_endpoint_and_cache(self):
        import io, json, re
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from app import create_server
        class Fake:
            reader=object();state='ready';error=None;calls=0
            def recognize_uid(self,image):
                self.calls+=1
                return {'uid':'51206386631','confidence':98}
        engine=Fake();server=create_server(engine,Path(__file__).resolve().parents[1]/'ui')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url) as response:
                token=json.loads(re.search(r'window.LV_PYTHON=(\{.*?\});',response.read().decode())[1])['token']
            output=io.BytesIO();Image.new('RGB',(400,300)).save(output,'PNG');body=output.getvalue()
            def post(key):return urlopen(Request(url+'/api/uid',body,{'Content-Type':'image/png','X-LV-Token':key}))
            with self.assertRaises(HTTPError) as rejected:post('wrong')
            self.assertEqual(rejected.exception.code,403)
            for _ in range(2):
                with post(token) as response:self.assertEqual(json.load(response)['uid'],'51206386631')
            self.assertEqual(engine.calls,1)
        finally:
            server.shutdown();server.server_close();thread.join()

class NativeUidTests(unittest.TestCase):
    def test_native_bridge_reads_without_http(self):
        import io,base64
        from desktop_support import DesktopApi
        image=Image.new('RGB',(400,300));data=io.BytesIO();image.save(data,'PNG')
        api=DesktopApi('test.log');sizes=[]
        def recognize(image):sizes.append(image.size);return {'uid':'51206386631','confidence':99}
        api._engine=SimpleNamespace(recognize_uid=recognize)
        self.assertEqual(api.read_uid(base64.b64encode(data.getvalue()).decode())['uid'],'51206386631')
        self.assertEqual(sizes,[(400,300)])
        api._engine=None
        with self.assertRaises(RuntimeError):api.read_uid(base64.b64encode(data.getvalue()).decode())

class SelectedUidTests(unittest.TestCase):
    def test_only_numbers_accepted_in_explicit_region(self):
        engine=LevelEngine('unused');engine.warm=lambda **kwargs:None
        engine._readtext=lambda *args,**kwargs:[item('51206386631')]
        self.assertIsNone(engine.recognize_uid(Image.new('RGB',(2000,1400)))['uid'])
        self.assertEqual(engine.recognize_uid(Image.new('RGB',(300,40)),cropped=True)['uid'],'51206386631')
        engine._readtext=lambda *args,**kwargs:[item('51206386631'),item('1234567890',x=40)]
        self.assertIsNone(engine.recognize_uid(Image.new('RGB',(300,40)),cropped=True)['uid'])
