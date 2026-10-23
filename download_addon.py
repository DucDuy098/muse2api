"""Persisted local export of completed image/video tasks; no remote fetches."""
import asyncio
import json
import os
import shutil
import threading
import time
from pathlib import Path
from fastapi import Depends, HTTPException, Request


def copy_result(media_dir, folder, task):
    name = (task.get('result') or {}).get('filename', '')
    if not name or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Tên tệp kết quả không hợp lệ')
    source = (Path(media_dir) / name).resolve()
    if source.parent != Path(media_dir).resolve():
        raise ValueError('Tệp nằm ngoài thư viện')
    from media_names import reserve
    account=task.get('account') or (task.get('result') or {}).get('account_id')
    if account:
        from account_media import account_folder
        folder=account_folder(folder,account)
    with source.open('rb') as src:
        target, dst = reserve(folder, task.get('kind','video' if source.suffix in ('.mp4','.webm','.mov') else 'image'), source.suffix)
        try:
            with dst: shutil.copyfileobj(src, dst)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return str(target)


def install(g):
    app, auth, store = g['app'], g['auth'], g['store']
    config_path = Path(getattr(g['CFG'], 'data_dir', Path(g['BASE_DIR']) / 'data')) / 'download_settings.json'
    lock = threading.RLock()
    state = {'enabled': False, 'folder': '', 'since': 0, 'saved': {}, 'pending': {}, 'error': ''}
    if config_path.exists():
        state.update(json.loads(config_path.read_text('utf-8')))

    def save():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = config_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False), 'utf-8')
        tmp.replace(config_path)

    @app.get('/v1/download-settings')
    def settings(_=Depends(auth)):
        with lock:
            return {k: v for k, v in state.items() if k not in ('saved', 'pending')} | {'saved_count': len(state['saved'])}

    def queue_result(result, kind):
        # Called only after engine.generate has finished writing the local file.
        # Includes synchronous API images as well as async/batch tasks.
        with lock:
            if state['enabled'] and result.get('filename'):
                name = result['filename']
                state['pending'][name] = {'id': 'media', 'kind': kind, 'status': 'completed',
                                         'created_at': int(time.time()), 'account':result.get('account_id'), 'result': {'filename': name}}
                save()

    g['_queue_local_download'] = queue_result

    @app.post('/v1/download-settings')
    async def update(request: Request, _=Depends(auth)):
        data = await request.json()
        enabled, folder = data.get('enabled'), data.get('folder', '')
        if not isinstance(enabled, bool) or not isinstance(folder, str):
            raise HTTPException(400, 'Cài đặt không hợp lệ')
        folder = folder.strip()
        if enabled or folder:
            path = Path(folder)
            if not folder or not path.is_absolute() or not path.is_dir():
                raise HTTPException(400, 'Chọn thư mục có sẵn trên máy chạy Muse2API')
            folder = str(path.resolve())
        with lock:
            if enabled and not state['enabled']:
                state['since'] = int(time.time())
            state.update(enabled=enabled, folder=folder, error='')
            save()
        return settings()

    picker_lock = threading.Lock()

    @app.post('/v1/download-settings/choose-folder')
    async def choose(_=Depends(auth)):
        def dialog():
            if os.name != 'nt':
                raise HTTPException(400, 'Nhập đường dẫn thư mục trên máy chủ')
            if not picker_lock.acquire(blocking=False):
                raise HTTPException(409, 'Cửa sổ chọn thư mục đang mở')
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                try:
                    return filedialog.askdirectory(parent=root, title='Chọn thư mục lưu ảnh / video Muse2API',
                                                   initialdir=state['folder'] or str(Path.home()))
                finally:
                    root.destroy()
            finally:
                picker_lock.release()
        return {'folder': await asyncio.to_thread(dialog)}

    stop = threading.Event()

    def worker():
        while not stop.wait(2):
            try:
                with lock:
                    if not state['enabled']:
                        continue
                    for task in list(state['pending'].values()) + store.list_tasks(100000):
                        if task.get('kind') not in ('image', 'video') or task.get('status') != 'completed':
                            continue
                        if task.get('created_at', 0) < state['since']:
                            continue
                        name = (task.get('result') or {}).get('filename', '')
                        key = state['folder'] + '|' + name
                        if key in state['saved']:
                            if name in state['pending']:
                                del state['pending'][name]
                                save()
                            continue
                        try:
                            target = copy_result(g['CFG'].media_dir, state['folder'], task)
                            state['saved'][key] = target
                            state['pending'].pop(name, None)
                            state['error'] = ''
                        except (OSError, ValueError) as exc:
                            state['error'] = str(exc)
                        save()
            except Exception as exc:
                with lock:
                    state['error'] = str(exc)

    @app.on_event('startup')
    def start():
        threading.Thread(target=worker, daemon=True, name='local-media-export').start()

    @app.on_event('shutdown')
    def shutdown():
        stop.set()
