import io,json,re,sys,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_server

class CacheTests(unittest.TestCase):
    def test_unknown_name_not_cached_and_manual_retry_bypasses_known_cache(self):
        class Fake:
            reader=object();state='ready';error=None;calls=0;known=False
            def recognize(self,image,logical_size=None):
                self.calls+=1
                return {'lv':7,'weapon':'AUG' if self.known else 'OTHER','name_known':self.known}
        engine=Fake();server=create_server(engine,Path(__file__).resolve().parents[1]/'ui')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(url) as response:token=json.loads(re.search(r'window.LV_PYTHON=(\{.*?\});',response.read().decode())[1])['token']
            payload=io.BytesIO();Image.new('RGB',(400,300)).save(payload,'PNG')
            def post(force=False):
                with urlopen(Request(url+'/api/ocr',payload.getvalue(),{'Content-Type':'image/png','X-LV-Token':token,'X-LV-Force':'1' if force else '0'})) as response:return json.load(response)
            post();post();self.assertEqual(engine.calls,2)
            engine.known=True;post();self.assertTrue(post()['cached']);self.assertEqual(engine.calls,3)
            self.assertNotIn('cached',post(True));self.assertEqual(engine.calls,4)
        finally:server.shutdown();server.server_close();thread.join()
