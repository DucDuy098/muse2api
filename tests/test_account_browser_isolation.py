"""Real Chromium: simultaneous startup, separate cookie jars, no shared-context fallback."""
import os,socket,sys,tempfile,threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):os.environ.pop(key,None)
os.environ['NO_PROXY']=os.environ['no_proxy']='127.0.0.1,localhost'
from engine import MuseEngine,MuseGenerationError
from windows_standalone import detect_browser
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'<html><body>Local cookie isolation fixture</body></html>')
with tempfile.TemporaryDirectory(dir=ROOT/'work',ignore_cleanup_errors=True) as tmp:
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 cfg=SimpleNamespace(chromium=detect_browser({}),cdp_port=port,profile_dir=tmp+'/profile',data_dir=tmp,download_dir=tmp+'/downloads',home_dir=tmp,extra_path='')
 engine=MuseEngine(cfg);barrier=threading.Barrier(2)
 def run(value):
  engine.start();pid=engine.proc.pid;page=engine._open_page();engine.page=page
  try:
   context=engine.current_context_id
   assert context
   page.send('Network.setCookie',{'name':'account_fixture','value':value,'domain':'127.0.0.1','path':'/'})
   barrier.wait(timeout=15)
   page.send('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/'})
   import time
   for _ in range(50):
    if page.js('document.readyState')=='complete':break
    time.sleep(.05)
   assert page.js('document.cookie')=='account_fixture='+value
   return pid,context
  finally:engine.close_current_page()
 try:
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['A','B']))
  assert results[0][0]==results[1][0] and results[0][1]!=results[1][1]
  assert not engine._active_contexts
 finally:engine.stop();server.shutdown();server.server_close()
 # Context creation failures must not fall back to a shared ordinary tab.
 engine.browser=SimpleNamespace(send=lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('fixture')))
 try:engine._open_page()
 except MuseGenerationError:pass
 else:raise AssertionError('shared-context fallback permitted')
print('PASS real Chromium simultaneous startup uses one process; 2 accounts have isolated cookies/contexts; shared-context fallback blocked')
