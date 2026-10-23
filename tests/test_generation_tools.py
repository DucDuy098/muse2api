"""Offline acceptance for 1.6.7: retry, reports, durable refs-once and safe short names."""
import os,sys,asyncio,tempfile,time,json,base64,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_async_images import Client
from media_names import reserve
PNG='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
class QueryClient(Client):
 async def request(self,method,path,**kw):
  if '?' not in path:return await super().request(method,path,**kw)
  original=self.app;parts=urlsplit(path)
  async def wrapped(scope,receive,send):
   scope.update(path=parts.path,raw_path=parts.path.encode(),query_string=parts.query.encode());await original(scope,receive,send)
  self.app=wrapped
  try:return await super().request(method,path,**kw)
  finally:self.app=original
async def check():
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  os.environ.update(MUSE2API_HOME=tmp,MUSE2API_PROFILE_ROOT=tmp,MUSE2API_KEY='qa-only')
  import app,batch_addon
  batch_addon.time=type('Clock',(),{'time':staticmethod(time.time),'sleep':staticmethod(lambda t:time.sleep(.02))})
  app.engine.start=lambda:None;app.engine.close_current_page=lambda:None
  calls=[];fail={'once','batch failure'}
  app._renew_and_persist=lambda aid,**kw:app.store.get_account(aid)
  app._sync_cookies=lambda aid:None
  app.store.accounts.append({'id':'fixture','cookies':{'fixture':'not-real'},'enabled':True})
  app.ACCOUNT_POOL.acquire=lambda **kw:{'id':kw.get('account_id') or 'fixture','cookies':{}}
  app.ACCOUNT_POOL.release=lambda _:None
  def generate(cookies,prompt,expect='video',**kw):
   app.engine.page=type('Page',(),{'js':lambda _,s:kw.get('thread_url') or 'https://muse.ai/thread/fixture'})()
   calls.append((prompt,kw.get('reference_image')))
   if kw.get('on_sent'):kw['on_sent']()
   for token in list(fail):
    if prompt.endswith(token):fail.remove(token);raise app.MuseGenerationError('fixture failure after sending')
   target,stream=reserve(app.CFG.media_dir,expect,'.mp4' if expect=='video' else '.png')
   with stream:stream.write(b'fixture')
   return {'filename':target.name,'kind':expect,'size':7,'path':str(target)}
  app.engine.generate=generate
  async with QueryClient(app.app,{'Authorization':'Bearer qa-only'}) as c:
   async def wait_task(tid):
    for _ in range(500):
     t=app.store.get_task(tid)
     if t['status'] in ('completed','failed'):return t
     await asyncio.sleep(.01)
    raise AssertionError(t)
   args={'prompt':'once','reference_images':[PNG],'reference_roles':['character'],'generation_mode':'coherent','sequence_id':'fixture_sequence','continuity_notes':'Same yellow coat','duration':10,'size':'1280x720'}
   r=await c.request('POST','/v1/videos',json_data=args);tid=r.json()['id'];assert (await wait_task(tid))['status']=='failed'
   saved=json.loads(Path(app.CFG.data_dir,'generation_sequences.json').read_text(encoding='utf-8'));assert saved['fixture_sequence']['references_sent']
   r=await c.get('/v1/task-tools/'+tid+'/request');assert r.json()['request']['reference_images']==[PNG]
   r=await c.request('POST','/v1/task-tools/'+tid+'/retry',json_data={});assert r.status_code==200,r.body
   newtid=r.json()['id'];task=await wait_task(newtid);assert task['status']=='completed',task
   assert calls[0][1]==[PNG] and calls[1][1] is None
   assert (await c.request('POST','/v1/task-tools/'+tid+'/retry',json_data={})).status_code==409
   assert (await c.request('POST','/v1/task-tools/'+newtid+'/retry',json_data={})).status_code==409
   r=await c.get('/v1/task-tools/report?statuses=failed');assert len(r.json()['items'])==1 and r.json()['items'][0]['status']=='failed'
   assert (await c.get('/v1/task-tools/report?statuses=nonsense')).status_code==400
   media=(await c.get('/admin/media')).json()['media'];assert media[0]['name']=='video_001.mp4' and media[0]['prompt']=='once'
   app.store.delete_task(newtid);assert (await c.get('/admin/media')).json()['media'][0]['prompt']=='once'
   # Persisted sequence is reloaded; the next send still omits images.
   from generation_sequence import install
   install(vars(app))
   args['prompt']='third scene';r=await c.request('POST','/v1/videos',json_data=args);assert (await wait_task(r.json()['id']))['status']=='completed';assert calls[-1][1] is None
   for scene in ('Independent 1','Independent 2'):
    r=await c.request('POST','/v1/videos',json_data={'prompt':scene,'reference_images':[PNG]});await wait_task(r.json()['id']);assert calls[-1][1]==[PNG]
   # Batch failed rows only, same sequence, completed row is never replayed.
   r=await c.request('POST','/v1/batches',json_data={'kind':'video','prompts':['first scene','batch failure','last scene'],'generation_mode':'coherent','reference_images':[PNG]});bid=r.json()['id']
   for _ in range(500):
    b=next(x for x in (await c.get('/v1/batches')).json() if x['id']==bid)
    if b.get('paused'):break
    await asyncio.sleep(.01)
   assert [r['status'] for r in b['items']]==['completed','failed','queued'],b
   failedtid=b['items'][1]['task_id']
   assert (await c.request('POST','/v1/task-tools/'+failedtid+'/retry',json_data={})).status_code==409
   report=(await c.get('/v1/batches/'+bid+'/report?statuses=failed,queued')).json()['items'];assert len(report)==2
   before=len(calls);r=await c.request('POST','/v1/batches/'+bid+'/retry-failed',json_data={});assert r.status_code==200,r.body
   for _ in range(500):
    b=next(x for x in (await c.get('/v1/batches')).json() if x['id']==bid)
    if all(r['status']=='completed' for r in b['items']):break
    await asyncio.sleep(.01)
   assert all(r['status']=='completed' for r in b['items']),b
   assert len(calls)==before+2 and all(x[1] is None for x in calls[before:])
   assert b['items'][1]['attempts']==2 and b['items'][1]['previous_attempts'][0]['task_id']==failedtid
   assert app.store.get_task(failedtid)['retry_task_id']==b['items'][1]['task_id']
   assert (await c.request('POST','/v1/task-tools/'+failedtid+'/retry',json_data={})).status_code==409
   archive=Path(app.CFG.data_dir,'generation_requests.json').read_text(encoding='utf-8');assert PNG not in archive
   assert len(list(Path(app.CFG.data_dir,'generation_references').glob('*.json')))==1
   assert all('reference_images' not in x for x in (await c.get('/v1/batches')).json())
   fail.add('image failure')
   r=await c.request('POST','/v1/batches',json_data={'kind':'image','prompts':['image failure','image followup'],'generation_mode':'coherent','reference_images':[PNG]});imagebid=r.json()['id']
   for _ in range(500):
    imagebatch=next(x for x in (await c.get('/v1/batches')).json() if x['id']==imagebid)
    if imagebatch.get('paused'):break
    await asyncio.sleep(.01)
   assert imagebatch['items'][0]['status']=='failed'
   r=await c.request('POST','/v1/batches/'+imagebid+'/retry-failed',json_data={});assert r.status_code==200,r.body
   for _ in range(500):
    imagebatch=next(x for x in (await c.get('/v1/batches')).json() if x['id']==imagebid)
    if all(x['status']=='completed' for x in imagebatch['items']):break
    await asyncio.sleep(.01)
   assert all(x['status']=='completed' for x in imagebatch['items']),imagebatch
   assert imagebatch['items'][0]['attempts']==2 and calls[-1][1] is None
   r=await QueryClient(app.app,{}).get('/v1/task-tools/report');assert r.status_code==401
  await asyncio.sleep(.12)
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  def create(_):
   path,stream=reserve(tmp,'video','.mp4')
   with stream:stream.write(b'unchanged')
   return path.name
  with ThreadPoolExecutor(max_workers=8) as pool:names=list(pool.map(create,range(30)))
  assert len(set(names))==30 and 'video_001.mp4' in names and 'video_030.mp4' in names
 print('PASS 1.6.7: refs once including failure/restart, independent refs each turn, safe sequential names x30, private request archive, prompt catalog, explicit retry dedup/batch ordering, filtered reports/auth')
# Check the real engine's send-confirmation boundary without a browser.
from engine import MuseEngine,MuseGenerationError
from types import SimpleNamespace
engine=object.__new__(MuseEngine);events=[]
engine.ensure_page=lambda *a,**kw:None;engine.reset_thread=lambda **kw:None
engine._scroll_bottom=lambda:None;engine._attach_image=lambda refs:events.append('upload');engine._clear_attachments=lambda:None
engine.attachments=lambda:[];engine._agent_count=lambda:0;engine._send=lambda p:'clicked'
engine._wait_attachment=lambda *a,**kw:{'src':'fixture'};engine.retrieve_attachment=lambda *a:{'filename':'fixture.mp4'}
engine.generate({},'scene',reference_image=[PNG],on_sent=lambda:events.append('sent'))
assert events==['upload','sent']
events.clear();engine._send=lambda p:'unconfirmed'
try:engine.generate({},'scene',reference_image=[PNG],on_sent=lambda:events.append('sent'))
except MuseGenerationError:pass
else:raise AssertionError('Unconfirmed send must fail')
assert events==['upload']
asyncio.run(check())
