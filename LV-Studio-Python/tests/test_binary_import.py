import sys,tempfile,threading,unittest,json,re
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_server
from desktop_support import DesktopApi
class BinaryImportTests(unittest.TestCase):
 def test_exact_binary_requires_token_and_granted_id(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'index.html').write_text('<head></head>');im=root/'a.png';im.write_bytes(b'original-no-reencode')
   api=DesktopApi('test.log');api._import_root=root;api._import_files={'allowed':im}
   server=create_server(SimpleNamespace(),root,api);threading.Thread(target=server.serve_forever,daemon=True).start()
   try:
    base='http://127.0.0.1:'+str(server.server_port)
    with urlopen(base) as response: token=json.loads(re.search(r'window.LV_PYTHON=(.*?);',response.read().decode())[1])['token']
    with self.assertRaises(HTTPError) as bad:urlopen(base+'/api/import-image/allowed')
    self.assertEqual(bad.exception.code,403)
    with urlopen(Request(base+'/api/import-image/allowed',headers={'X-LV-Token':token})) as response:
     self.assertEqual(response.read(),im.read_bytes());self.assertEqual(response.headers['Content-Type'],'image/png')
    with self.assertRaises(HTTPError) as bad:urlopen(Request(base+'/api/import-image/not-granted',headers={'X-LV-Token':token}))
    self.assertEqual(bad.exception.code,404)
    outside=root.parent/'outside-test.png';outside.write_bytes(b'outside')
    try:
     api._import_files['escape']=outside
     with self.assertRaises(ValueError):api.read_acc_bytes('escape')
    finally:outside.unlink()
   finally:server.shutdown();server.server_close()
