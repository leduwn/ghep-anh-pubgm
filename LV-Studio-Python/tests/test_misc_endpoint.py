import sys,tempfile,threading,unittest,json,re,io
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_server
class MiscEndpointTests(unittest.TestCase):
 def test_auth_and_independent_of_ocr_startup(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'index.html').write_text('<head></head>')
   server=create_server(SimpleNamespace(error='OCR unavailable'),root);threading.Thread(target=server.serve_forever,daemon=True).start()
   try:
    base='http://127.0.0.1:'+str(server.server_port)
    with urlopen(base) as response:token=json.loads(re.search(r'window.LV_PYTHON=(.*?);',response.read().decode())[1])['token']
    data=io.BytesIO();Image.new('RGB',(200,230),'red').save(data,'PNG');data=data.getvalue()
    with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/api/misc',data=data,headers={'Content-Type':'image/png'}))
    self.assertEqual(error.exception.code,403)
    with urlopen(Request(base+'/api/misc',data=data,headers={'Content-Type':'image/png','X-LV-Token':token})) as response:
     result=json.load(response);self.assertFalse(result['detected']);self.assertEqual(result['rects'],[])
   finally:server.shutdown();server.server_close()
