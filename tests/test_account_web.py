"""Render actual admin/batch assets in isolated Chromium against a local fake API."""
import base64,json,os,socket,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cdp import CDP
from windows_standalone import detect_browser
import requests
accounts=[{'id':'accA','label':'Tài khoản A','enabled':True,'cookie_count':4,'ok':True},
          {'id':'accB','label':'Tài khoản B','enabled':True,'cookie_count':4,'ok':True}]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  path=self.path.split('?')[0];assets={'/admin':'admin.html','/batch':'batch.html','/video_reference_picker.js':'video_reference_picker.js','/studio_panels.js':'studio_panels.js'}
  if path in assets:
   content=(ROOT/assets[path]).read_bytes();mime='application/javascript' if path.endswith('.js') else 'text/html; charset=utf-8'
  else:
   payload={'accounts':accounts} if path=='/admin/accounts' else [] if path=='/v1/batches' else {'tasks':[],'media':[],'user_ids':[],'enabled':False,'folder':'','token_set':False,'api_key':'fixture'}
   content=json.dumps(payload).encode();mime='application/json'
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(content)
session=requests.Session();session.trust_env=False
with tempfile.TemporaryDirectory(dir=ROOT/'work',ignore_cleanup_errors=True) as tmp:
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{server.server_port}'
 proc=subprocess.Popen([detect_browser({}),'--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking','--remote-allow-origins=*',f'--remote-debugging-port={port}',f'--user-data-dir={tmp}/profile',base+'/admin?key=fixture'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 page=None
 try:
  for _ in range(80):
   try:
    tabs=session.get(f'http://127.0.0.1:{port}/json',timeout=1).json();target=next(x for x in tabs if x.get('type')=='page');page=CDP(target['webSocketDebuggerUrl'])
    if page.js("document.getElementById('imgAccount')?.options.length===3"):break
    page.close();page=None
   except Exception:pass
   time.sleep(.1)
  assert page,'account pickers did not load'
  assert page.js("['imgAccount','vidAccount','chatAccount','taskAccount','mediaAccount'].every(id=>document.getElementById(id).options.length>=3)")
  first=page.js("(()=>{$('vidAccount').value='accA';$('vidGenerationMode').value='coherent';return generationSettings('vid')})()")
  if isinstance(first,str):first=json.loads(first)
  second=page.js("(()=>{$('vidAccount').value='accB';return generationSettings('vid')})()")
  if isinstance(second,str):second=json.loads(second)
  assert first['account_id']=='accA' and second['account_id']=='accB' and first['sequence_id']!=second['sequence_id']
  page.js("$('chatAccount').value='accA';$('chatAccount').dispatchEvent(new Event('change'))")
  assert page.js("JSON.parse(localStorage.getItem('muse2api_chat_sessions'))[0].account_id")=='accA'
  count=page.js("(async()=>{await videoRefs.add([new File(['# Scene script'],'kich-ban.md',{type:'text/markdown'})]);return videoRefs.payload().reference_files.length})()",await_promise=True)
  assert count==1
  assert page.js("videoRefs.payload().reference_files[0].name")=='kich-ban.md'
  assert page.js("document.querySelector('#singleVideoReferences input').accept.includes('.xlsx')")
  page.js("localStorage.setItem('muse2api_key','fixture')")
  page.send('Page.navigate',{'url':base+'/batch'})
  for _ in range(60):
   try:
    if page.js("document.getElementById('batchAccount')?.options.length===3"):break
   except Exception:pass
   time.sleep(.1)
  assert page.js("document.getElementById('batchAccount').options.length")==3
  assert page.js("(()=>{$('batchAccount').value='accA';$('batchAccount').dispatchEvent(new Event('change'));return $('concurrency').value==='1'&&$('concurrency').disabled})()")
  print('PASS actual Chromium admin/batch account selectors, per-account sequences/chat, named MD picker and sequential account batch controls')
 finally:
  if page:
   try:page.send('Browser.close')
   except Exception:pass
   page.close()
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
  server.shutdown();server.server_close()
