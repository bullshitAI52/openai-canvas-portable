import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as app
import engine
from PIL import Image

class PortableTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();app.DATA=Path(cls.tmp.name);app.OUTPUT=app.DATA/'outputs';engine.CONFIG=app.DATA/'config.local.json'
  cls.http=app.serve(0);cls.url=f'http://127.0.0.1:{cls.http.server_port}'
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
 def request(self,path,data=None,headers=None):
  h={'Content-Type':'application/json'} if data is not None else {}
  h.update(headers or {})
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
  try:r=urllib.request.urlopen(req,timeout=5)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,r.read()
 def test_page_and_assets(self):
  for path in ['/openai-canvas','/openai-canvas/assets/app.js','/openai-canvas/assets/style.css']:
   code,body=self.request(path);self.assertEqual(code,200);self.assertTrue(body)
 def test_status_no_secret(self):
  engine.save_key('sk-test-not-real')
  status,body=self.request('/openai-canvas/status');self.assertEqual(status,200);self.assertNotIn(b'sk-test-not-real',body)
 def test_cross_origin_and_host(self):
  for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'}]:
   code,_=self.request('/openai-canvas/workflow',{'version':1,'nodes':[],'edges':[]},headers);self.assertEqual(code,403)
 def test_malformed_payload(self):
  self.assertEqual(self.request('/openai-canvas/llm',[])[0],400)
  self.assertEqual(self.request('/openai-canvas/llm',{'prompt':2})[0],400)
 def test_settings_permission_and_validation(self):
  self.assertEqual(self.request('/openai-canvas/settings',{'api_key':'bad\nkey'})[0],400)
  self.assertEqual(self.request('/openai-canvas/settings',{'api_key':'sk-test-not-real'})[0],200)
  if os.name != 'nt':self.assertEqual(engine.CONFIG.stat().st_mode&0o777,0o600)
 def test_workflow_roundtrip(self):
  workflow={'version':1,'nodes':[{'id':'i1','type':'image','src':'data:image/png;base64,AA=='}],'edges':[],'view':{'x':2,'y':3,'z':1}}
  self.assertEqual(self.request('/openai-canvas/workflow',workflow)[0],200)
  self.assertEqual(json.loads(self.request('/openai-canvas/workflow')[1])['workflow'],workflow)
  self.assertEqual(self.request('/openai-canvas/workflow',{**workflow,'api_key':'forbidden'})[0],400)
 def test_llm_six_images(self):
  refs=['reference']*6
  with patch.object(engine,'refine',return_value='test prompt') as call:
   code,body=self.request('/openai-canvas/llm',{'prompt':'test','model':'test','images':refs});self.assertEqual(code,200);self.assertEqual(json.loads(body)['text'],'test prompt');self.assertEqual(call.call_args.args[1],refs)
 def test_generate_and_download(self):
  image=io.BytesIO();Image.new('RGB',(10,10),'red').save(image,format='PNG');encoded=base64.b64encode(image.getvalue()).decode()
  with patch.object(engine,'generate',return_value=[encoded]):
   code,body=self.request('/openai-canvas/generate',{'prompt':'test','model':'test','images':[],'size':'1536x864','quality':'auto','count':1});self.assertEqual(code,200)
   file=json.loads(body)['images'][0];code,body=self.request('/view?filename='+file['filename']);self.assertEqual(code,200);self.assertEqual(body,image.getvalue())
 def test_no_path_traversal(self):
  for path in ['/view?filename=../config.local.json','/openai-canvas/assets/engine.py','/config.local.json']:
   self.assertEqual(self.request(path)[0],404)
 def test_invalid_count(self):
  with patch.object(engine,'generate') as call:
   self.assertEqual(self.request('/openai-canvas/generate',{'prompt':'test','model':'test','count':1.5})[0],400);call.assert_not_called()
 def test_concurrent_guard(self):
  entered=threading.Event();release=threading.Event()
  def slow(*args):entered.set();release.wait(5);return 'prompt'
  data={'prompt':'test','model':'test','images':[]}
  with patch.object(engine,'refine',side_effect=slow):
   thread=threading.Thread(target=lambda:self.request('/openai-canvas/llm',data));thread.start();self.assertTrue(entered.wait(3))
   try:self.assertEqual(self.request('/openai-canvas/llm',data)[0],409);self.assertEqual(self.request('/openai-canvas/shutdown',{})[0],409)
   finally:release.set();thread.join()
 def test_error_releases_lock(self):
  with patch.object(engine,'refine',side_effect=RuntimeError('test error')):
   self.assertEqual(self.request('/openai-canvas/llm',{'prompt':'test','model':'test','images':[]})[0],502)
  self.assertFalse(app.api_lock.locked())
 def test_corrupted_image(self):
  with self.assertRaises(ValueError):engine.decode_image('data:image/png;base64,bm90IGltYWdl')
 def test_exif(self):
  image=Image.new('RGB',(32,24));exif=Image.Exif();exif[274]=6;out=io.BytesIO();image.save(out,format='JPEG',exif=exif)
  decoded=engine.decode_image('data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode());self.assertEqual(Image.open(io.BytesIO(decoded)).size,(24,32))

if __name__=='__main__':unittest.main(verbosity=1)
