"""20-scene coherence, language, ordered batches and failure pause; offline."""
import sys,os,asyncio,tempfile,base64,json,time,re
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_async_images import Client
PNG='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()
async def check():
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  os.environ.update(MUSE2API_HOME=tmp,MUSE2API_PROFILE_ROOT=tmp,MUSE2API_KEY='qa-only')
  import app,batch_addon
  batch_addon.time=SimpleNamespace(time=time.time,sleep=lambda t:time.sleep(.01))
  calls=[];leases=[];current={'url':''};threads=[]
  app.engine.start=lambda:None;app.engine.close_current_page=lambda:None
  app.engine.page=SimpleNamespace(js=lambda s:current['url'])
  def acquire(**kw):leases.append(kw);return {'id':kw.get('account_id') or 'acc_fixture','cookies':{}}
  app.ACCOUNT_POOL.acquire=acquire;app.ACCOUNT_POOL.release=lambda _:None
  def generate(cookies,prompt,expect='image',**kw):
   url=kw.get('thread_url')
   if not url:url='https://muse.ai/thread/'+str(len(threads)+1);threads.append(url)
   current['url']=url;app.engine.page=SimpleNamespace(js=lambda s:url);calls.append({'prompt':prompt,'url':url,'refs':kw.get('reference_image'),'kind':expect})
   if kw.get('on_sent'):kw['on_sent']()
   if 'FAIL_THIS_SCENE' in prompt:raise app.MuseGenerationError('Fixture scene failed')
   name=str(len(calls))+('.mp4' if expect=='video' else '.png');p=Path(app.CFG.media_dir)/name;p.write_bytes(b'fixture')
   return {'filename':name,'kind':expect,'size':7,'path':str(p)}
  app.engine.generate=generate
  for prompt,lang in [('Cảnh chú mèo đi trên cỏ','vi'),('Wide shot, a spaceship lands','en')]:
   p=app.build_video_prompt(app.VideoRequest(prompt=prompt,size='16:9'))
   assert prompt in p and not re.search('[\u4e00-\u9fff]',p)
   assert ('Tạo một' in p)==(lang=='vi')
   assert ('Create one' in p)==(lang=='en')
  assert 'Tạo một' in app.build_video_prompt(app.VideoRequest(prompt='Wide shot',prompt_language='vi'))
  async with Client(app.app,{'Authorization':'Bearer qa-only'}) as c:
   r=await c.request('POST','/v1/batches',json_data={'kind':'video','prompts':['Scene '+str(i) for i in range(1,21)],'generation_mode':'coherent','reference_images':[PNG,PNG],'reference_roles':['character','background'],'continuity_notes':'Red suit, metallic spaceship','prompt_language':'en','size':'1280x720','concurrency':1})
   assert r.status_code==200,r.body;bid=r.json()['id']
   for _ in range(500):
    history=(await c.get('/v1/batches')).json();b=next(x for x in history if x['id']==bid)
    if all(x['status']=='completed' for x in b['items']):break
    await asyncio.sleep(.01)
   else:raise AssertionError(b)
   assert len(calls)==20 and len(threads)==1
   assert len({x['url'] for x in calls})==1 and calls[0]['refs']==[PNG,PNG] and all(x['refs'] is None for x in calls[1:])
   assert all('Red suit' in x['prompt'] and 'Do not reuse characters' not in x['prompt'] for x in calls)
   assert all(x.get('account_id')=='acc_fixture' for x in leases[1:])
   assert [x['prompt'].split('Scene instructions:\n')[1] for x in calls]==['Scene '+str(i) for i in range(1,21)]
   saved=json.loads(Path(app.CFG.data_dir,'generation_sequences.json').read_text(encoding='utf-8'))
   assert saved[bid]['completed_scenes']==20 and saved[bid]['thread_url']==threads[0]
   bad=await c.request('POST','/v1/batches',json_data={'kind':'video','prompts':['a'],'generation_mode':'coherent','concurrency':2});assert bad.status_code==400
   # Image coherence, distinct new sequence, and automatic language selection.
   before=len(calls)
   r=await c.request('POST','/v1/batches',json_data={'kind':'image','prompts':['Cảnh nhân vật bước vào nhà','Wide shot, character at window'],'generation_mode':'coherent','reference_images':[PNG],'reference_roles':['character']})
   assert r.status_code==200;imageid=r.json()['id']
   for _ in range(300):
    b=next(x for x in (await c.get('/v1/batches')).json() if x['id']==imageid)
    if all(x['status']=='completed' for x in b['items']):break
    await asyncio.sleep(.01)
   assert len(calls)==before+2 and len(threads)==2
   assert 'Tạo một ảnh' in calls[-2]['prompt'] and 'Create one image' in calls[-1]['prompt']
   # Independent API generations must create separate threads and omit sequence state.
   before=len(calls)
   for prompt in ('Independent shot one','Independent shot two'):
    r=await c.request('POST','/v1/videos',json_data={'prompt':prompt,'generation_mode':'independent'})
    assert r.status_code==200
    tid=r.json()['id']
    for _ in range(200):
     task=(await c.get('/v1/videos/'+tid)).json()
     if task['status'] in ('completed','failed'):break
     await asyncio.sleep(.01)
    assert task['status']=='completed',task
   assert calls[-1]['url']!=calls[-2]['url'] and len(calls)==before+2
   # A failed coherent scene pauses before sending the next one.
   before=len(calls)
   r=await c.request('POST','/v1/batches',json_data={'kind':'video','prompts':['FAIL_THIS_SCENE','Never auto send'],'generation_mode':'coherent'})
   assert r.status_code==200;failureid=r.json()['id']
   for _ in range(300):
    b=next(x for x in (await c.get('/v1/batches')).json() if x['id']==failureid)
    if b.get('paused'):break
    await asyncio.sleep(.01)
   assert b['paused'] and b['items'][1]['status']=='queued' and len(calls)==before+1
   await c.request('POST','/v1/batches/'+failureid+'/stop',json_data={})
   await asyncio.sleep(.2)
 print('PASS 20 ordered video scenes share thread/account/refs, coherent images, new sequence separation, Vietnamese/English prompts, concurrency validation, failure pause')
asyncio.run(check())
