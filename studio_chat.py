"""Stateful desktop/web chat: send only the new prompt to the same Muse thread."""
import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from telegram_bot import atomic_json


class StudioChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    account_id: str | None = Field(default=None,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    prompt: str = Field(min_length=1, max_length=30000)
    resume_only: bool = False


def thread_url(value):
    u = urlparse(str(value or ''))
    return str(value) if u.scheme == 'https' and u.hostname == 'muse.ai' and u.path.startswith('/thread/') and u.path != '/thread/new' else None


def install(g):
    app, cfg, engine, pool = g['app'], g['CFG'], g['engine'], g['ACCOUNT_POOL']
    path = Path(cfg.data_dir) / 'studio_chat_sessions.json'
    try: sessions = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError, ValueError): sessions = {}
    lock = threading.Lock()
    busy = set()

    def reply(req):
        if not req.prompt.strip(): raise HTTPException(400, 'Tin nhắn đang trống')
        with lock:
            if req.session_id in busy: raise HTTPException(409, 'Hội thoại này đang trả lời')
            busy.add(req.session_id)
            session = dict(sessions.get(req.session_id, {}))
        acc = None
        acquired = False
        result = {}
        try:
            if req.resume_only and not session:
                raise HTTPException(409, 'Hội thoại từ bản cũ chưa lưu địa chỉ Muse. Bấm Chat mới một lần để khởi tạo phiên; các lượt sau sẽ tiếp tục cùng hội thoại.')
            if req.account_id and session.get('account_id') and session['account_id']!=req.account_id:
                raise HTTPException(409,'Hội thoại thuộc tài khoản khác. Bấm Chat mới khi đổi tài khoản.')
            timeout = cfg.chat_timeout
            acquired = g['GEN_LOCK'].acquire(timeout=timeout)
            if not acquired: raise HTTPException(503, 'Muse đang bận; chưa gửi tin nhắn')
            acc = pool.acquire(account_id=session.get('account_id') or req.account_id, timeout=timeout)
            if session and not session.get('thread_url'):
                raise HTTPException(409, 'Chưa lưu được địa chỉ hội thoại Muse. Bấm Chat mới để bắt đầu lại.')
            engine.start()
            text = ''.join(engine.chat_stream(acc['cookies'], req.prompt.strip(), acc.get('cookies_exp'), timeout,
                        account_id=acc['id'], thread_url=session.get('thread_url'), on_result=result.update))
            url = thread_url(result.get('thread_url'))
            with lock:
                sessions[req.session_id] = {'account_id': acc['id'], 'thread_url': url}
                atomic_json(path, sessions)
            media = []
            for item in result.get('media', []):
                public = {k: item.get(k) for k in ('filename', 'kind', 'size', 'mime')}
                public['url'] = g['media_url'](item['filename'])
                from account_media import index_result
                index_result(cfg.media_dir,item,acc['id'])
                g.get('_remember_chat_media',lambda *a:None)(item,acc['id'],req.prompt)
                media.append(public)
                g.get('_queue_local_download', lambda *args: None)(item, item['kind'])
            errors = result.get('media_errors', [])
            if not url: errors.append('Muse chưa cung cấp địa chỉ để tiếp tục hội thoại này. Hãy bấm Chat mới cho lần sau.')
            return {'account_id':acc['id'], 'session_id': req.session_id, 'message': {'role': 'assistant', 'content': text, 'media': media}, 'warnings': errors}
        except HTTPException: raise
        except Exception as exc: raise HTTPException(502, str(exc)) from exc
        finally:
            if acquired:
                # A timeout after sending must not cause the next turn to start
                # a new conversation. Preserve the created thread before close.
                if acc and getattr(engine, 'page', None):
                    try:
                        url = thread_url(engine.page.js('window.location.href'))
                        if url:
                            with lock:
                                sessions[req.session_id] = {'account_id': acc['id'], 'thread_url': url}
                                atomic_json(path, sessions)
                    except Exception: pass
                engine.close_current_page()
                if acc: pool.release(acc['id'])
                g['GEN_LOCK'].release()
            with lock: busy.discard(req.session_id)

    g['studio_chat_reply'] = reply

    @app.post('/v1/studio/chat')
    async def chat(req: StudioChatRequest, _=Depends(g['auth'])):
        return await asyncio.to_thread(reply, req)
