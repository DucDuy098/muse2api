"""Offline acceptance: 100 scenes per account run in parallel, pinned retries and files."""
import asyncio, base64, json, os, re, sys, tempfile, threading, time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_async_images import Client
from reference_files import validate_files

class QueryClient(Client):
    async def request(self,method,path,**kw):
        if '?' not in path:return await super().request(method,path,**kw)
        original=self.app;path,query=path.split('?',1)
        async def wrapped(scope,receive,send):
            scope.update(path=path,raw_path=path.encode(),query_string=query.encode());await original(scope,receive,send)
        self.app=wrapped
        try:return await super().request(method,path,**kw)
        finally:self.app=original

async def check():
 with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
    os.environ.update(MUSE2API_HOME=tmp,MUSE2API_PROFILE_ROOT=tmp,MUSE2API_KEY='qa-only',MUSE2API_CONCURRENCY='1')
    import app,batch_addon
    from media_names import reserve
    from engine import MuseGenerationError
    a=app.store.add_account({'fixture':'a'},'Account A')['id'];b=app.store.add_account({'fixture':'b'},'Account B')['id']
    app.engine.start=lambda:None;app.engine.close_current_page=lambda:None
    app._renew_and_persist=lambda aid,**kw:app.store.get_account(aid)
    app._sync_cookies=lambda aid:None
    batch_addon.time=SimpleNamespace(time=time.time,sleep=lambda seconds:time.sleep(.005))
    calls=[];active=set();peak=[0];guard=threading.Lock();failed=set()
    def generate(cookies,prompt,expect='video',**kw):
        aid=kw['account_id']
        with guard:
            assert aid not in active,'same account concurrent'
            active.add(aid);peak[0]=max(peak[0],len(active));calls.append((aid,prompt,kw))
        app.engine.page=SimpleNamespace(js=lambda _:kw.get('thread_url') or 'https://muse.ai/thread/'+aid)
        try:
            if kw.get('on_sent'):kw['on_sent']()
            time.sleep(.012)
            if 'FAIL_ONCE' in prompt and aid not in failed:
                failed.add(aid);raise MuseGenerationError('fixture failure')
            path,stream=reserve(app.CFG.media_dir,expect,'.mp4' if expect=='video' else '.png')
            with stream:stream.write(b'fixture media')
            return {'filename':path.name,'kind':expect,'size':13,'path':str(path)}
        finally:
            with guard:active.remove(aid)
    app.engine.generate=generate
    doc={'name':'kịch bản.md','data':'data:text/markdown;base64,'+base64.b64encode('Kịch bản tham chiếu'.encode()).decode()}
    async with QueryClient(app.app,{'Authorization':'Bearer qa-only'}) as client:
        async def post(path,data):
            r=await client.request('POST',path,json_data=data);assert r.status_code in (200,202),(path,r.body)
            return r.json()
        async def task(tid):
            for _ in range(1200):
                t=app.store.get_task(tid)
                if t['status'] in ('completed','failed'):return t
                await asyncio.sleep(.005)
            raise AssertionError('task timeout')
        bids=[]
        for aid,prefix in ((a,'AA'),(b,'BB')):
            bids.append((await post('/v1/batches',{'kind':'video','account_id':aid,'prompts':[f'{prefix}_{i}' for i in range(100)],'reference_files':[doc]}))['id'])
        duplicate=await client.request('POST','/v1/batches',json_data={'kind':'video','account_id':a,'prompts':['extra']})
        assert duplicate.status_code==409
        for _ in range(2500):
            batches=(await client.get('/v1/batches')).json()
            chosen=[x for x in batches if x['id'] in bids]
            if all(all(r['status']=='completed' for r in x['items']) for x in chosen):break
            await asyncio.sleep(.008)
        else:raise AssertionError([(x['id'],[r['status'] for r in x['items']]) for x in chosen])
        assert peak[0]==2,peak
        for aid,prefix in ((a,'AA'),(b,'BB')):
            order=[int(re.search(prefix+r'_(\d+)',p).group(1)) for account,p,kw in calls if account==aid and prefix+'_' in p]
            assert order==list(range(100)),order
        assert all(kw['reference_image']==[doc] for _,_,kw in calls)
        assert all('reference_files' not in item for item in batches),'private attachment payload exposed'
        # Default retry stays on actual account, including failures; another account starts independently.
        t=await task((await post('/v1/videos',{'prompt':'FAIL_ONCE','account_id':a}))['id'])
        assert t['status']=='failed' and t['account']==a
        retried=await task((await post('/v1/task-tools/'+t['id']+'/retry',{}))['id'])
        assert retried['status']=='completed' and retried['account']==a
        other=await task((await post('/v1/task-tools/'+t['id']+'/retry?account_id='+b,{}))['id'])
        assert other['account']==b and other['generation_mode']=='independent'
        request=(await client.get('/v1/task-tools/'+retried['id']+'/request')).json()['request'];assert request['account_id']==a
        # Sequence pins both account and documents; changed account is rejected before another send.
        args={'prompt':'scene one','account_id':a,'generation_mode':'coherent','sequence_id':'seqA','reference_files':[doc]}
        first=await task((await post('/v1/videos',args))['id']);assert first['status']=='completed'
        args['prompt']='scene two';second=await task((await post('/v1/videos',args))['id']);assert second['status']=='completed'
        assert calls[-2][2]['reference_image']==[doc] and calls[-1][2]['reference_image'] is None
        # Failed rows may be copied to another account without replaying completed rows.
        bad_batch=await post('/v1/batches',{'kind':'video','account_id':a,'prompts':['copy failed row'],'generation_mode':'independent'})
        for _ in range(500):
            items=(await client.get('/v1/batches')).json();batch=next(x for x in items if x['id']==bad_batch['id'])
            if batch['items'][0]['status']=='completed':break
            await asyncio.sleep(.005)
        original=app.store.get_task(batch['items'][0]['task_id'])
        app.store.update_task(original['id'],status='failed',error='fixture explicit failure')
        copied=await post('/v1/batches/'+bad_batch['id']+'/clone-failed?account_id='+b,{})
        for _ in range(500):
            items=(await client.get('/v1/batches')).json();clone=next(x for x in items if x['id']==copied['id'])
            if clone['items'][0]['status']=='completed':break
            await asyncio.sleep(.005)
        assert clone['account_id']==b and clone['generation_mode']=='independent' and len(clone['items'])==1 and clone['items'][0]['status']=='completed'
        # Legacy/automatic batch retries pin the account actually used, even when the pool prefers another.
        auto=await post('/v1/batches',{'kind':'video','prompts':['auto recovery']})
        for _ in range(500):
            batches=(await client.get('/v1/batches')).json();auto_batch=next(x for x in batches if x['id']==auto['id'])
            if auto_batch['items'][0]['status']=='completed':break
            await asyncio.sleep(.005)
        auto_task=app.store.get_task(auto_batch['items'][0]['task_id']);actual=auto_task['account']
        app.store.update_task(auto_task['id'],status='failed',error='fixture failure')
        app.store.get_account(actual)['last_used']=time.time()+9999
        app.store.get_account(b if actual==a else a)['last_used']=0
        await post('/v1/batches/'+auto['id']+'/retry-failed',{})
        for _ in range(500):
            batches=(await client.get('/v1/batches')).json();auto_batch=next(x for x in batches if x['id']==auto['id'])
            if auto_batch['items'][0]['status']=='completed':break
            await asyncio.sleep(.005)
        assert auto_batch['items'][0]['status']=='completed' and app.store.get_task(auto_batch['items'][0]['task_id'])['account']==actual
        count=len(calls);args.update(account_id=b,prompt='wrong account')
        wrong=await task((await post('/v1/videos',args))['id']);assert wrong['status']=='failed' and len(calls)==count
        # File folder membership, filtering and export attribution survive deleting task rows.
        media=(await client.get('/admin/media?account_id='+a)).json()['media']
        assert media and all(m['account_id']==a for m in media)
        for m in media:assert Path(tmp,'data/media/accounts',a,m['name']).is_file()
        app.store.delete_task(first['id'])
        assert any(m['task_id']==first['id'] for m in (await client.get('/admin/media?account_id='+a)).json()['media'])
        report=(await client.get('/v1/task-tools/report?account_id='+a)).json()['items'];assert all(r['account']==a for r in report)
        # Chat account stays pinned and cannot be changed in an existing conversation.
        def chat(cookies,prompt,*args,**kw):
            kw['on_result']({'thread_url':'https://muse.ai/thread/chatA'});yield 'Complete reply'
        app.engine.chat_stream=chat
        await post('/v1/studio/chat',{'session_id':'chatA','account_id':a,'prompt':'hello'})
        mismatch=await client.request('POST','/v1/studio/chat',json_data={'session_id':'chatA','account_id':b,'prompt':'next'})
        assert mismatch.status_code==409
        invalid=await client.request('POST','/v1/videos',json_data={'account_id':'missing','prompt':'invalid'});assert invalid.status_code==400
        for file in ({'name':'bad.exe','data':doc['data']},{'name':'../script.md','data':doc['data']},{'name':'bad.md','data':'data:text/plain;base64,!!!'}):
            bad=await client.request('POST','/v1/videos',json_data={'prompt':'invalid document','reference_files':[file]});assert bad.status_code==400
    await asyncio.sleep(.05)
 print('PASS 200 ordered scenes across 2 simultaneous accounts; pinned retry/chat/sequence; docs once; account folders, filters and report attribution; invalid files rejected')

if __name__=='__main__':asyncio.run(check())
