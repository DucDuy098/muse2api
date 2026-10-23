"""Private request archive, explicit failed-task retry and filtered reports."""
import hashlib
import json
import threading
from pathlib import Path
from fastapi import Depends, HTTPException
from telegram_bot import atomic_json

STATUSES={'completed','queued','processing','failed','interrupted','cancelled','running','submitting'}
def report_rows(rows,statuses=''):
    selected=set(filter(None,statuses.split(',')))
    if selected-STATUSES: raise HTTPException(400,'Trạng thái xuất không hợp lệ')
    return [{k:r.get(k) for k in ('index','id','task_id','kind','prompt','status','error','url','created_at','attempts','account','account_id')} |
            {'filename':(r.get('result') or {}).get('filename','')} for r in rows if not selected or r.get('status') in selected]

def install(g):
    app,auth,store=g['app'],g['auth'],g['store']
    path=Path(g['CFG'].data_dir)/'generation_requests.json'
    try: requests=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (ValueError,OSError): requests={}
    catalog_path=path.with_name('media_prompts.json')
    try:catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {}
    except (ValueError,OSError):catalog={}
    lock=threading.RLock(); retrying=set()
    original_update=store.update_task
    def update(tid,**kw):
        task=original_update(tid,**kw)
        filename=(kw.get('result') or {}).get('filename')
        if filename and task:
            with lock:
                catalog[filename]={k:task.get(k) for k in ('id','prompt','api_prompt','kind','account')};atomic_json(catalog_path,catalog)
        return task
    store.update_task=update
    g['_media_prompt_catalog']=catalog
    def chat_media(item,account,prompt):
        with lock:
            catalog[item['filename']]={'account':account,'prompt':prompt,'kind':item['kind'],'id':None}
            atomic_json(catalog_path,catalog)
    g['_remember_chat_media']=chat_media
    references_dir=path.parent/'generation_references'
    def resolve_request(tid):
        data=dict(requests[tid]);digest=data.pop('_reference_set',None)
        if digest:
            if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise HTTPException(409,'Dữ liệu ảnh mẫu đã lưu không hợp lệ')
            try:data.update(json.loads((references_dir/(digest+'.json')).read_text(encoding='utf-8')))
            except (OSError,ValueError):raise HTTPException(409,'Không đọc được ảnh mẫu đã lưu; chọn lại ảnh trước khi tạo')
        return data
    def remember(tid,req):
        data=req.model_dump(by_alias=True)
        refs={k:data.pop(k) for k in ('reference_files','reference_images','reference_image','image','image_url','images') if data.get(k)}
        with lock:
            if refs:
                digest=hashlib.sha256(json.dumps(refs,sort_keys=True).encode()).hexdigest()
                refpath=references_dir/(digest+'.json')
                if not refpath.exists():atomic_json(refpath,refs)
                data['_reference_set']=digest
            requests[tid]=data;atomic_json(path,requests)
    g['_remember_generation_request']=remember
    @app.get('/v1/task-tools/report')
    def report(statuses:str='',account_id:str|None=None,_=Depends(auth)):
        rows=store.list_tasks(100000)
        if account_id:rows=[r for r in rows if (r.get('account') or 'unassigned')==account_id]
        return {'items':report_rows(rows,statuses)}
    @app.get('/v1/task-tools/{tid}/request')
    def request_data(tid:str,_=Depends(auth)):
        with lock:
            if tid not in requests:raise HTTPException(409,'Tác vụ cũ chưa lưu đủ thông số. Nhập lại prompt và chọn ảnh mẫu để tạo lại.')
            task=store.get_task(tid) or next((item for item in catalog.values() if item.get('id')==tid),None)
            if not task:raise HTTPException(404,'Không tìm thấy tác vụ')
            data=resolve_request(tid)
            data['account_id']=task.get('account') or data.get('account_id')
            return {'kind':task['kind'],'request':data}
    @app.post('/v1/task-tools/{tid}/retry')
    async def retry(tid:str,account_id:str|None=None,_=Depends(auth)):
        with lock:
            task=store.get_task(tid)
            if not task:raise HTTPException(404,'Không tìm thấy tác vụ')
            if task['status']!='failed':raise HTTPException(409,'Chỉ tạo lại tác vụ lỗi')
            if (task.get('retry_task_id') and not account_id) or tid in retrying:raise HTTPException(409,'Đã tạo lại tác vụ này; xem tác vụ mới')
            if tid not in requests:raise HTTPException(409,'Tác vụ cũ chưa lưu đủ thông số. Sao chép prompt và chọn lại ảnh mẫu.')
            # Batch retries must update the owning row, maintaining order and progress.
            if g.get('_batch_owns_task',lambda x:False)(tid):raise HTTPException(409,'Tác vụ thuộc một lô. Dùng Tạo lại prompt lỗi tại mục Excel / TXT.')
            data=resolve_request(tid)
            chosen=account_id or task.get('account') or data.get('account_id')
            if chosen:
                acc=store.get_account(chosen)
                if not acc or not acc.get('enabled',True) or not acc.get('cookies'):raise HTTPException(409,'Tài khoản gốc không khả dụng; chọn tài khoản khác để tạo riêng')
            data['account_id']=chosen
            if account_id:
                data.update(generation_mode='independent',sequence_id=None)
            retrying.add(tid)
        try:
            if task['kind']=='video':result=await g['create_video'](g['VideoRequest'](**data),_=None)
            else:result=json.loads(g['create_image_task'](g['ImageRequest'](**data),idempotency_key=None,_=None).body)
            store.update_task(tid,retry_task_id=result['id']);store.update_task(result['id'],retry_of=tid)
            return result
        finally:
            with lock:retrying.discard(tid)
