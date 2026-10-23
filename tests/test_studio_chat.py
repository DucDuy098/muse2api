"""Stateful chat API: new text only, pinned account/thread, media, auth."""
import asyncio,sys,tempfile,os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_async_images import Client
async def check():
 with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
  os.environ.update(MUSE2API_HOME=tmp,MUSE2API_PROFILE_ROOT=tmp,MUSE2API_KEY='qa-only')
  import app
  calls=[];accounts=[];closed=[]
  app.engine.start=lambda:None;app.engine.close_current_page=lambda:closed.append(True)
  def acquire(**kwargs):accounts.append(kwargs);return {'id':'account_fixture','cookies':{}}
  app.ACCOUNT_POOL.acquire=acquire;app.ACCOUNT_POOL.release=lambda i:None
  def reply(cookies,prompt,*args,**kw):
   calls.append((prompt,kw.get('thread_url')))
   name='reply.mp4';Path(app.CFG.media_dir,name).write_bytes(b'video fixture')
   kw['on_result']({'thread_url':'https://muse.ai/thread/test_thread','media':[{'filename':name,'kind':'video','size':13,'mime':'video/mp4'}]})
   yield 'Đã tạo video'
  app.engine.chat_stream=reply
  async with Client(app.app,{'Authorization':'Bearer qa-only'}) as c:
   for prompt in ('Tin nhắn đầu','Tin nhắn tiếp'):
    r=await c.request('POST','/v1/studio/chat',json_data={'session_id':'test_session','prompt':prompt})
    assert r.status_code==200,r.body
    result=r.json();assert result['message']['media'][0]['filename']=='reply.mp4'
    assert result['message']['media'][0]['url'].endswith('/reply.mp4')
    assert 'path' not in result['message']['media'][0]
   assert calls==[('Tin nhắn đầu',None),('Tin nhắn tiếp','https://muse.ai/thread/test_thread')],calls
   assert accounts[1]['account_id']=='account_fixture' and len(closed)==2
   count=len(calls)
   r=await c.request('POST','/v1/studio/chat',json_data={'session_id':'legacy_session','prompt':'Continue','resume_only':True});assert r.status_code==409
   assert len(calls)==count,'Legacy chat must not silently start a new Muse thread'
   r=await c.request('POST','/v1/studio/chat',json_data={'session_id':'test_session','prompt':' '});assert r.status_code==400
   r=await c.request('POST','/v1/studio/chat',json_data={'session_id':'../oops','prompt':'Hi'});assert r.status_code==422
  async with Client(app.app,{}) as c:
   r=await c.request('POST','/v1/studio/chat',json_data={'session_id':'session','prompt':'Hi'});assert r.status_code==401
  saved=json.loads(Path(tmp,'data/studio_chat_sessions.json').read_text(encoding='utf-8'))
  assert saved['test_session']['thread_url'].endswith('/test_thread')
  assert not any('cookies' in x for x in saved.values())
  from fastapi import FastAPI
  from studio_chat import install,StudioChatRequest
  reloaded=dict(app.__dict__);reloaded['app']=FastAPI();install(reloaded)
  reloaded['studio_chat_reply'](StudioChatRequest(session_id='test_session',prompt='After restart'))
  assert calls[-1]==('After restart','https://muse.ai/thread/test_thread')
  reloaded['studio_chat_reply'](StudioChatRequest(session_id='new_session',prompt='New chat'))
  assert calls[-1]==('New chat',None)
 print('PASS chat sends only latest prompt, keeps Muse thread/account, returns video metadata, auth and empty input validation')
asyncio.run(check())
