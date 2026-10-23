"""Durable batch admission; never automatically replay interrupted generation."""
import asyncio, json, threading, time, uuid, io, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

def parse_file(name, data):
    if len(data)>5*1024*1024: raise ValueError("File tối đa 5 MB")
    if name.lower().endswith('.txt'):
        return [x.strip() for x in data.decode('utf-8-sig').splitlines() if x.strip()]
    if not name.lower().endswith('.xlsx'): raise ValueError("Chỉ hỗ trợ .txt UTF-8 và .xlsx; hãy lưu .xls thành .xlsx")
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist())>20*1024*1024: raise ValueError("Excel quá lớn")
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
        sheets=sorted(x for x in z.namelist() if x.startswith('xl/worksheets/sheet') and x.endswith('.xml'))
        if not sheets: return []
        rows=[]
        for row in ET.fromstring(z.read(sheets[0])).findall('.//m:row',ns):
            cells={}
            for c in row.findall('m:c',ns):
                col=''.join(x for x in c.get('r','') if x.isalpha())
                v=c.find('m:v',ns)
                value=v.text if v is not None and v.text else ''
                if c.get('t')=='s': value=shared[int(value)]
                elif c.get('t')=='inlineStr': value=''.join(t.text or '' for t in c.findall('.//m:t',ns))
                cells[col]=value
            rows.append(cells)
        if not rows: return []
        col=next((k for k,v in rows[0].items() if v.strip().lower() in ('prompt','mô tả','mo ta')),None)
        selected=rows[1:] if col else rows
        col=col or 'A'
        return [r.get(col,'').strip() for r in selected if r.get(col,'').strip()]

def install(g):
    from download_addon import install as install_downloads
    install_downloads(g)
    app,auth,store=g['app'],g['auth'],g['store']
    path=Path(g['CFG'].data_dir)/'batches.json'
    lock=threading.RLock()
    batches=json.loads(path.read_text('utf-8')) if path.exists() else {}
    workers=set()
    def save():
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(batches,ensure_ascii=False),encoding='utf-8'); tmp.replace(path)
    for b in batches.values():
        for r in b['items']:
            if r['status'] in ('queued','submitting','running'):
                r['status']='interrupted'; r['error']='Dịch vụ đã khởi động lại. Kiểm tra Tác vụ trước khi tạo lại.'
    if batches: save()
    def refresh(b):
        for r in b['items']:
            if r.get('task_id'):
                t=store.get_task(r['task_id'])
                if t and t['status'] in ('completed','failed'):
                    if t['status']=='failed' and r['status']!='failed' and b.get('generation_mode')=='coherent':
                        b.update(paused=True,pause_reason='Cảnh '+str(r['index'])+' lỗi; kiểm tra trước khi tiếp tục.')
                    r.update(account=t.get('account') or b.get('account_id'),status=t['status'],url=t.get('url'),error=t.get('error'),result=t.get('result'))
    def worker(bid):
        while True:
            with lock:
                b=batches[bid]; refresh(b)
                active=sum(r['status'] in ('submitting','running') for r in b['items'])
                row=next((r for r in b['items'] if r['status']=='queued'),None)
                if not row and not active: save(); return
                if b.get('paused') or active>=b['concurrency']: row=None
                if row: row['status']='submitting'; row['attempts']=row.get('attempts',0)+1; save()
            if row:
                try:
                    args={'prompt':row['prompt'],'size':b['size'],'generation_mode':b.get('generation_mode','independent'),
                          'account_id':row.get('account') or b.get('account_id'), 'reference_files':b.get('reference_files',[]),
                          'sequence_id':bid if b.get('generation_mode')=='coherent' else None,
                          'continuity_notes':b.get('continuity_notes',''),'prompt_language':b.get('prompt_language','auto')}
                    args['reference_images']=b.get('reference_images') or None
                    args['reference_roles']=b.get('reference_roles') or None
                    if b['kind']=='image':
                        res=g['create_image_task'](g['ImageRequest'](**args),idempotency_key=bid+':'+str(row['index'])+':'+str(row.get('attempts',1)),_=None)
                        result=json.loads(res.body)
                    else:
                        args['duration']=b['duration']
                        result=asyncio.run(g['create_video'](g['VideoRequest'](**args),_=None))
                    with lock:
                        if row.get('previous_attempts'):
                            previous=row['previous_attempts'][-1].get('task_id')
                            if previous:
                                store.update_task(previous,retry_task_id=result['id'])
                                store.update_task(result['id'],retry_of=previous)
                        row.update(task_id=result['id'],status='running'); save()
                except Exception as e:
                    with lock:
                        row.update(status='failed',error=str(e))
                        if b.get('generation_mode')=='coherent':b.update(paused=True,pause_reason='Cảnh lỗi; kiểm tra trước khi tiếp tục.')
                        save()
            time.sleep(1)
    def start_worker(bid):
        with lock:
            if bid in workers:return
            workers.add(bid)
        def run():
            try:worker(bid)
            finally:
                with lock:
                    workers.discard(bid)
                    restart=not batches[bid].get('paused') and any(r['status']=='queued' for r in batches[bid]['items'])
                if restart:start_worker(bid)
        threading.Thread(target=run,daemon=True).start()
    g['_batch_owns_task']=lambda tid:any(r.get('task_id')==tid or any(a.get('task_id')==tid for a in r.get('previous_attempts',[])) for b in batches.values() for r in b['items'])
    @app.get('/v1/batches/{bid}/report')
    def report(bid:str,statuses:str='',_=Depends(auth)):
        from task_tools import report_rows
        with lock:
            if bid not in batches:raise HTTPException(404,'Không tìm thấy lô')
            refresh(batches[bid])
            return {'id':bid,'items':report_rows(batches[bid]['items'],statuses)}
    @app.get('/batch',response_class=HTMLResponse)
    def page(): return (Path(g['BASE_DIR'])/'batch.html').read_text('utf-8')
    @app.get('/video_reference_picker.js')
    def reference_picker():
        return Response((Path(g['BASE_DIR'])/'video_reference_picker.js').read_text('utf-8'),media_type='application/javascript')
    @app.get('/studio_panels.js')
    def studio_panels():
        return Response((Path(g['BASE_DIR'])/'studio_panels.js').read_text('utf-8'),media_type='application/javascript')
    @app.post('/v1/batches/import')
    async def import_file(request:Request,_=Depends(auth)):
        try: prompts=parse_file(request.headers.get('X-Filename',''),await request.body())
        except Exception as e: raise HTTPException(400,str(e))
        if len(prompts)>500: raise HTTPException(400,'Tối đa 500 prompt')
        return {'prompts':prompts}
    @app.post('/v1/batches')
    async def create(request:Request,_=Depends(auth)):
        d=await request.json(); prompts=d.get('prompts',[])
        if not isinstance(prompts,list) or not 1<=len(prompts)<=500 or any(not isinstance(x,str) or not x.strip() or len(x)>30000 for x in prompts): raise HTTPException(400,'Cần 1–500 prompt hợp lệ')
        if d.get('kind') not in ('image','video'): raise HTTPException(400,'Loại không hợp lệ')
        try: concurrency=int(d.get('concurrency',1)); duration=int(d.get('duration',10))
        except (ValueError,TypeError): raise HTTPException(400,'Thông số không hợp lệ')
        if not 1<=concurrency<=2 or not 1<=duration<=10: raise HTTPException(400,'Song song 1–2; thời lượng 1–10 giây')
        mode=d.get('generation_mode','independent');lang=d.get('prompt_language','auto');notes=d.get('continuity_notes','')
        if mode not in ('independent','coherent') or lang not in ('auto','vi','en') or not isinstance(notes,str) or len(notes)>10000: raise HTTPException(400,'Chế độ/ngôn ngữ/quy ước chuỗi không hợp lệ')
        if mode=='coherent' and concurrency!=1: raise HTTPException(400,'Chuỗi đồng bộ phải chạy lần lượt, song song = 1')
        from video_references import validate_references
        try: references,roles=validate_references(d.get('reference_images',[]),d.get('reference_roles'))
        except ValueError as exc: raise HTTPException(400,str(exc))
        from reference_files import validate_files
        try: documents=validate_files(d.get('reference_files',[]))
        except ValueError as exc: raise HTTPException(400,str(exc))
        account=d.get('account_id') or None
        if account:
            acc=store.get_account(account)
            if not acc or not acc.get('enabled',True) or not acc.get('cookies'):raise HTTPException(400,'Tài khoản không khả dụng')
            if concurrency!=1:raise HTTPException(400,'Mỗi tài khoản chạy lần lượt; đặt song song = 1 cho lô')
        size=d.get('size','1024x1024')
        if size not in ('1024x1024','720x1280','1280x720','1080x1920'): raise HTTPException(400,'Kích thước không hợp lệ')
        with lock:
            if any(b.get('account_id')==account and any(r['status'] in ('queued','submitting','running') for r in b['items']) for b in batches.values()): raise HTTPException(409,'Tài khoản này đang có lô chưa xong. Chọn tài khoản khác hoặc hoàn tất/dừng lô cũ.')
            bid='batch_'+uuid.uuid4().hex
            batches[bid]={'id':bid,'created_at':time.time(),'kind':d['kind'],'size':size,'duration':duration,'concurrency':concurrency,'items':[{'index':i+1,'prompt':x.strip(),'status':'queued'} for i,x in enumerate(prompts)]}
            batches[bid].update(account_id=account,reference_files=documents,reference_images=references,reference_roles=roles,generation_mode=mode,prompt_language=lang,continuity_notes=notes); save()
        start_worker(bid)
        return {'id':bid}
    @app.get('/v1/batches')
    def listing(_=Depends(auth)):
        with lock:
            for b in batches.values(): refresh(b)
            return [dict({k:v for k,v in b.items() if k not in ('reference_images','reference_files')}, reference_count=len(b.get('reference_images',[]))+len(b.get('reference_files',[])),account_label=(store.get_account(b.get('account_id')) or {}).get('label',b.get('account_id') or 'Tự động'))
                    for b in reversed(list(batches.values()))]
    @app.post('/v1/batches/{bid}/{action}')
    def control(bid:str,action:str,account_id:str|None=None,_=Depends(auth)):
        with lock:
            if bid not in batches: raise HTTPException(404,'Không tìm thấy lô')
            b=batches[bid]
            refresh(b)
            if action=='clone-failed':
                import copy
                acc=store.get_account(account_id)
                if not acc or not acc.get('enabled',True) or not acc.get('cookies'):raise HTTPException(400,'Chọn tài khoản khả dụng để tạo riêng')
                if any(other.get('account_id')==account_id and any(r['status'] in ('queued','submitting','running') for r in other['items']) for other in batches.values()):raise HTTPException(409,'Tài khoản đích đang có lô chưa xong')
                failed=[r for r in b['items'] if r['status']=='failed']
                if not failed:raise HTTPException(409,'Không có prompt lỗi')
                clone=copy.deepcopy(b);newid='batch_'+uuid.uuid4().hex
                clone.update(id=newid,account_id=account_id,generation_mode='independent',concurrency=1,created_at=time.time(),paused=False,pause_reason='',copied_from=bid,items=[{'index':i+1,'prompt':r['prompt'],'status':'queued'} for i,r in enumerate(failed)])
                batches[newid]=clone;save();start_worker(newid)
                return {'ok':True,'id':newid}
            if action=='retry-failed':
                if any(r['status'] in ('submitting','running') for r in b['items']):raise HTTPException(409,'Chờ tác vụ đang chạy hoàn tất trước khi tạo lại')
                if any(other['id']!=bid and other.get('account_id')==b.get('account_id') and any(r['status'] in ('queued','submitting','running') for r in other['items']) for other in batches.values()):raise HTTPException(409,'Tài khoản này đang có lô khác')
                failed=[r for r in b['items'] if r['status']=='failed']
                if not failed:raise HTTPException(409,'Không có prompt lỗi để tạo lại')
                for r in failed:
                    r.setdefault('previous_attempts',[]).append({k:r.get(k) for k in ('task_id','error','status')})
                    r.update(status='queued',task_id=None,error=None,url=None,result=None)
                b.update(paused=False,pause_reason='')
            elif action in ('pause','resume'): b['paused']=action=='pause' 
            elif action=='stop':
                for r in b['items']:
                    if r['status']=='queued': r['status']='cancelled'
            else: raise HTTPException(400,'Thao tác không hợp lệ')
            save()
        if action in ('resume','retry-failed'):start_worker(bid)
        return {'ok':True}
