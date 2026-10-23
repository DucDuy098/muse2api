"""Pinned Muse thread/account for sequential character-consistent generations."""
import hashlib
import json
import threading
import time
from pathlib import Path
from fastapi import Depends
from telegram_bot import atomic_json
from studio_chat import thread_url


def install(g):
    path = Path(g['CFG'].data_dir) / 'generation_sequences.json'
    try: sequences = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError, ValueError): sequences = {}
    lock = threading.Lock()
    busy = set()

    def generate(sid, prompt, kind, timeout, refs, progress, acquired_callback, account_id=None, on_account=None):
        with lock:
            if sid in busy: raise g['MuseGenerationError']('Chuỗi đang tạo một cảnh; chờ hoàn tất rồi gửi cảnh tiếp theo')
            busy.add(sid); state = dict(sequences.get(sid, {}))
        engine, pool = g['engine'], g['ACCOUNT_POOL']
        held, acc, completed = False, None, False
        # Pre-1.6.7 sequences have already attached references on every completed turn.
        refs_sent = bool(state.get('references_sent', int(state.get('completed_scenes',0))>0))
        fingerprint = hashlib.sha256(json.dumps(refs,sort_keys=True).encode()).hexdigest() if refs else None
        if refs_sent and refs and state.get('reference_hash') and fingerprint!=state['reference_hash']:
            with lock: busy.discard(sid)
            raise g['MuseGenerationError']('Bộ ảnh mẫu đã thay đổi. Bấm Chuỗi mới để dùng bộ ảnh mới.')
        deadline = time.monotonic()+timeout
        def sent():
            nonlocal refs_sent
            if refs: refs_sent=True
            url=state.get('thread_url')
            if engine.page:url=thread_url(engine.page.js('window.location.href')) or url
            with lock:
                sequences[sid]={'account_id':acc['id'],'thread_url':url,'references_sent':refs_sent,
                                'reference_hash':state.get('reference_hash') or (fingerprint if refs_sent else None),
                                'completed_scenes':state.get('completed_scenes',0)}
                atomic_json(path,sequences)
        try:
            if account_id and state.get('account_id') and state['account_id'] != account_id: raise g['MuseGenerationError']('Chuỗi này thuộc tài khoản khác. Bấm Chuỗi mới khi đổi tài khoản.')
            if state and not state.get('thread_url'): raise g['MuseGenerationError']('Chưa lưu được hội thoại chuỗi. Bắt đầu chuỗi mới; không tự tạo cảnh tiếp ở hội thoại khác.')
            held = g['GEN_LOCK'].acquire(timeout=timeout)
            if not held: raise g['MuseGenerationError']('Hết thời gian chờ Muse rảnh')
            acc = pool.acquire(account_id=state.get('account_id') or account_id, timeout=max(1,int(deadline-time.monotonic())))
            if on_account: on_account(acc['id'])
            if acquired_callback: acquired_callback()
            engine.start()
            index = int(state.get('completed_scenes',0))+1
            result = engine.generate(acc['cookies'], prompt, expect=kind,
                        timeout=max(1,int(deadline-time.monotonic())), expires=acc.get('cookies_exp'), account_id=acc['id'],
                        on_progress=progress, reference_image=None if refs_sent else refs, thread_url=state.get('thread_url'), on_sent=sent)
            from account_media import index_result
            index_result(g['CFG'].media_dir,result,acc['id'])
            completed = True
            result.update(sequence_id=sid, scene_index=index)
            g.get('_queue_local_download',lambda *a:None)(result,kind)
            return result,acc['id']
        finally:
            if held:
                if acc:
                    url = state.get('thread_url')
                    if engine.page:
                        try: url = thread_url(engine.page.js('window.location.href')) or url
                        except Exception: pass
                    with lock:
                        sequences[sid]={'account_id':acc['id'],'thread_url':url,
                                        'references_sent':refs_sent, 'reference_hash':state.get('reference_hash') or (fingerprint if refs_sent else None),
                                        'completed_scenes':int(state.get('completed_scenes',0))+int(completed)}
                        atomic_json(path,sequences)
                engine.close_current_page()
                if acc: pool.release(acc['id'])
                g['GEN_LOCK'].release()
            with lock: busy.discard(sid)

    g['coherent_generate'] = generate

    @g['app'].get('/v1/generation-sequences')
    def listing(_=Depends(g['auth'])):
        with lock:
            return [{'id':sid,'completed_scenes':s.get('completed_scenes',0),'ready':bool(s.get('thread_url'))} for sid,s in sequences.items()]
