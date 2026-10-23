"""Native Tk desktop studio; no extra GUI framework or embedded browser needed."""
import base64
import json
import mimetypes
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import urllib.error
import urllib.request
import webbrowser

from batch_addon import parse_file
from telegram_bot import TelegramSettings, atomic_json
from video_references import validate_references
from windows_standalone import (ROOT, configure, contain_console_processes, detect_browser,
                                get_ports, local_environment, port_is_free)


class LocalAPIError(RuntimeError):
    def __init__(self, message, status, path):
        super().__init__(message)
        self.status, self.path = status, path


class LocalAPI:
    def __init__(self, env):
        self.base = 'http://127.0.0.1:' + env.get('MUSE2API_PORT', '18610')
        self.key = env.get('MUSE2API_KEY', '')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, body=None, method=None, timeout=30):
        raw = json.dumps(body).encode('utf-8') if body is not None else None
        request = urllib.request.Request(self.base + path, data=raw, method=method or ('POST' if raw is not None else 'GET'),
                                         headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                data = json.load(exc)
                error = data.get('detail') or data.get('error') or f'HTTP {exc.code}'
            except (ValueError, OSError):
                error = f'HTTP {exc.code}'
            if exc.code == 404 and path.startswith('/v1/telegram/'):
                error = 'Phiên dịch vụ đang chạy chưa có API Telegram mới. Khởi động lại dịch vụ để áp dụng bản cập nhật.'
            raise LocalAPIError(str(error), exc.code, path) from None
        except (urllib.error.URLError, OSError):
            raise RuntimeError('Chưa kết nối dịch vụ. Bấm Chạy dịch vụ rồi chờ trạng thái Sẵn sàng.') from None


class ReferenceList(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text='Ảnh mẫu — tối đa 8 ảnh, 5 MB/ảnh, tổng 20 MB', padding=8)
        self.items = []
        self.tree = ttk.Treeview(self, columns=('number', 'name', 'role'), show='headings', height=5, selectmode='browse')
        for name, title, width in [('number', '#', 40), ('name', 'Tên ảnh', 350), ('role', 'Vai trò', 170)]:
            self.tree.heading(name, text=title); self.tree.column(name, width=width)
        self.tree.pack(fill='x')
        row = ttk.Frame(self); row.pack(fill='x', pady=(8, 0))
        ttk.Button(row, text='Thêm ảnh…', command=self.add).pack(side='left')
        ttk.Button(row, text='Bỏ ảnh chọn', command=self.remove).pack(side='left', padx=6)
        ttk.Button(row, text='Bỏ tất cả', command=self.clear).pack(side='left')
        self.roles = {'Tham khảo': 'reference', 'Nhân vật': 'character', 'Bối cảnh': 'scene', 'Nền': 'background', 'Khung hình đầu': 'first_frame'}
        self.role = tk.StringVar(value='Tham khảo')
        box = ttk.Combobox(row, textvariable=self.role, values=list(self.roles), state='readonly', width=18)
        box.pack(side='left', padx=12); box.bind('<<ComboboxSelected>>', self.change_role)
        self.tree.bind('<<TreeviewSelect>>', self.selected)

    def add(self):
        paths = filedialog.askopenfilenames(parent=self, title='Chọn một hoặc nhiều ảnh mẫu', filetypes=[('Ảnh', '*.png *.jpg *.jpeg *.webp')])
        if not paths:
            return
        try:
            if len(self.items) + len(paths) > 8:
                raise ValueError('Tối đa 8 ảnh mẫu')
            new = []
            for raw in paths:
                path = Path(raw)
                if path.stat().st_size > 5 * 1024 * 1024:
                    raise ValueError('Mỗi ảnh tối đa 5 MB')
                mime = mimetypes.guess_type(path.name)[0]
                data = 'data:' + str(mime) + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
                new.append({'name': path.name, 'data': data, 'role': 'reference'})
            all_items = self.items + new
            validate_references([x['data'] for x in all_items], [x['role'] for x in all_items])
            self.items = all_items; self.render()
        except (ValueError, OSError) as exc:
            messagebox.showerror('Ảnh mẫu', str(exc), parent=self)

    def render(self):
        self.tree.delete(*self.tree.get_children())
        names = {v: k for k, v in self.roles.items()}
        for index, item in enumerate(self.items):
            self.tree.insert('', 'end', iid=str(index), values=(index + 1, item['name'], names[item['role']]))

    def selected(self, _=None):
        selected = self.tree.selection()
        if selected:
            role = self.items[int(selected[0])]['role']
            self.role.set(next(k for k, v in self.roles.items() if v == role))

    def change_role(self, _=None):
        selected = self.tree.selection()
        if selected:
            index = int(selected[0]); self.items[index]['role'] = self.roles[self.role.get()]
            self.render(); self.tree.selection_set(str(index))

    def remove(self):
        selected = self.tree.selection()
        if selected:
            self.items.pop(int(selected[0])); self.render()

    def clear(self):
        self.items = []; self.render()

    def payload(self):
        return {'reference_images': [x['data'] for x in self.items], 'reference_roles': [x['role'] for x in self.items]}


class DesktopStudio:
    def __init__(self, root=None):
        if root is None:
            return  # Qt's cooperative MRO initializes the controller explicitly.
        self.root = root
        root.title('Muse2API · Studio desktop')
        root.geometry('1120x820'); root.minsize(900, 690)
        configure(ROOT)
        self.env = local_environment(ROOT)
        self.api = LocalAPI(self.env)
        self.process, self.log_handle, self.ready = None, None, False
        self.events = queue.Queue()
        self.closing, self.checking = False, False
        self.service_log_offset = 0
        self.chat_busy = False
        self.active_media, self.active_batches = {}, {}
        self.history_path = ROOT / 'data' / 'desktop_chat.json'
        try:
            self.messages = json.loads(self.history_path.read_text('utf-8')) if self.history_path.exists() else []
        except (ValueError, OSError):
            self.messages = []
        style = ttk.Style(root); style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TNotebook.Tab', padding=(12, 7))
        root.option_add('*Text.font', 'Consolas 11')
        self.status = tk.StringVar(value='Chưa kết nối dịch vụ')
        top = ttk.Frame(root, padding=10); top.pack(fill='x')
        ttk.Label(top, text='Muse2API Studio', font=('Segoe UI', 14, 'bold')).pack(side='left', padx=(0, 16))
        ttk.Button(top, text='Chạy dịch vụ', command=self.start_service).pack(side='left')
        ttk.Button(top, text='Dừng dịch vụ', command=self.stop_service).pack(side='left', padx=6)
        ttk.Button(top, text='Mở Web', command=lambda: webbrowser.open(self.api.base + '/admin')).pack(side='left')
        ttk.Label(top, textvariable=self.status).pack(side='right')
        self.tabs = ttk.Notebook(root); self.tabs.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.chat_tab = self.page('Chat Muse'); self.media_tab = self.page('Tạo ảnh / video')
        self.batch_tab = self.page('Hàng loạt Excel / TXT'); self.library_tab = self.page('Thư viện / Tác vụ')
        self.accounts_tab = self.page('Tài khoản'); self.settings_tab = self.page('Cài đặt'); self.log_tab = self.page('Nhật ký')
        self.build_chat(); self.build_media(); self.build_batch(); self.build_library(); self.build_accounts(); self.build_settings()
        self.log_text = tk.Text(self.log_tab, state='disabled', wrap='word'); self.log_text.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.drain); root.after(500, self.refresh_status)

    def page(self, title):
        page = ttk.Frame(self.tabs, padding=10); self.tabs.add(page, text=title); return page

    def dispatch(self, function, success=None, failure=None):
        def work():
            try:
                result = function()
                if success:
                    self.events.put((success, result))
            except Exception as exc:
                self.events.put((failure or self.error, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def drain(self):
        if self.closing:
            return
        while not self.events.empty():
            callback, value = self.events.get_nowait()
            callback(value)
        self.root.after(100, self.drain)

    def error(self, text):
        self.status.set(str(text)); self.log(str(text))
        messagebox.showerror('Muse2API', str(text), parent=self.root)

    def log(self, text):
        # Keys/tokens must never appear in GUI logs.
        value = str(text).replace(self.api.key, '[API key]') if self.api.key else str(text)
        token = TelegramSettings(ROOT / 'data').read().get('token')
        if token:
            value = value.replace(token, '[Telegram token]')
        self.log_text.configure(state='normal'); self.log_text.insert('end', time.strftime('%H:%M:%S ') + value + '\n')
        self.log_text.see('end'); self.log_text.configure(state='disabled')

    def start_service(self):
        if self.process and self.process.poll() is None:
            self.status.set('Dịch vụ GUI đang chạy'); return
        try:
            port, cdp = get_ports(self.env)
            if not port_is_free(port):
                self.dispatch(lambda: self.api.call('/healthz', timeout=2), lambda _: self.status.set('Đã kết nối phiên dịch vụ đang chạy'))
                return
            if not port_is_free(cdp):
                raise RuntimeError(f'Cổng Chrome {cdp} đang được dùng. Dừng phiên cũ trước khi chạy GUI.')
            env = dict(self.env); env['MUSE2API_CHROMIUM'] = detect_browser(env)
            log_path = ROOT / 'data' / 'desktop_service.log'; log_path.parent.mkdir(exist_ok=True)
            self.log_handle = log_path.open('ab', buffering=0)
            python = ROOT / '.venv' / 'Scripts' / 'python.exe'
            command = ([sys.executable, '--service'] if getattr(sys, 'frozen', False) else
                       [str(python), str(ROOT / 'desktop_service.py')])
            self.process = subprocess.Popen(command, cwd=ROOT, env=env,
                                             stdout=self.log_handle, stderr=subprocess.STDOUT,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.status.set('Đang khởi động dịch vụ…'); self.log('Khởi động dịch vụ trong nền; đóng GUI sẽ dừng phiên này.')
        except (ValueError, OSError, RuntimeError) as exc:
            self.error(str(exc))

    def stop_service(self):
        if not self.process or self.process.poll() is not None:
            messagebox.showinfo('Dịch vụ', 'GUI không sở hữu phiên đang chạy. Dừng từ cửa sổ CMD đã mở phiên đó.', parent=self.root)
            return
        if (self.chat_busy or self.active_media or self.active_batches) and not messagebox.askyesno('Dừng dịch vụ', 'Có yêu cầu đang theo dõi. Dừng dịch vụ sẽ gián đoạn tác vụ chưa hoàn tất. Vẫn dừng?', parent=self.root):
            return
        self.process.terminate()
        self.status.set('Đang dừng dịch vụ…'); self.log('Đã yêu cầu dừng phiên GUI và Chrome riêng.')

    def refresh_status(self):
        if self.closing:
            return
        if not self.checking:
            self.checking = True
            self.dispatch(lambda: self.api.call('/healthz', timeout=2), self.connected, self.disconnected)
        log_path = ROOT / 'data' / 'desktop_service.log'
        if log_path.exists():
            try:
                with log_path.open('rb') as handle:
                    if log_path.stat().st_size < self.service_log_offset:
                        self.service_log_offset = 0
                    handle.seek(self.service_log_offset)
                    chunk = handle.read(32768)
                    self.service_log_offset = handle.tell()
                for line in chunk.decode('utf-8', errors='replace').splitlines():
                    if line.strip():
                        self.log(line)
            except OSError:
                pass
        self.root.after(2500, self.refresh_status)

    def connected(self, _):
        self.checking = False
        if not self.ready:
            self.ready = True; self.load_settings(); self.refresh_accounts(); self.refresh_library()
        self.status.set('Sẵn sàng · ' + self.api.base)

    def disconnected(self, _):
        self.checking = False; self.ready = False
        self.status.set('Dịch vụ chưa chạy — bấm Chạy dịch vụ')
        if self.process and self.process.poll() is not None:
            self.process = None
            if self.log_handle:
                self.log_handle.close(); self.log_handle = None

    def build_chat(self):
        self.transcript = tk.Text(self.chat_tab, wrap='word', state='disabled', height=20)
        self.transcript.pack(fill='both', expand=True)
        self.render_chat()
        self.chat_input = tk.Text(self.chat_tab, height=4, wrap='word'); self.chat_input.pack(fill='x', pady=8)
        self.chat_input.bind('<Control-Return>', lambda _: self.send_chat())
        row = ttk.Frame(self.chat_tab); row.pack(fill='x')
        self.chat_button = ttk.Button(row, text='Gửi (Ctrl+Enter)', command=self.send_chat); self.chat_button.pack(side='left')
        ttk.Button(row, text='Chat mới', command=self.new_chat).pack(side='left', padx=8)
        self.chat_status = tk.StringVar(); ttk.Label(row, textvariable=self.chat_status).pack(side='left')

    def render_chat(self):
        self.transcript.configure(state='normal'); self.transcript.delete('1.0', 'end')
        for message in self.messages:
            self.transcript.insert('end', ('Bạn' if message['role'] == 'user' else 'Muse') + ':\n' + message['content'] + '\n\n')
        self.transcript.see('end'); self.transcript.configure(state='disabled')

    def new_chat(self):
        if self.chat_busy:
            return
        self.chat_session_id = uuid.uuid4().hex
        atomic_json(ROOT / 'data' / 'desktop_chat_session.json', {'id': self.chat_session_id})
        self.messages = []; atomic_json(self.history_path, self.messages); self.render_chat()
        if hasattr(self,'save_account_chat'):self.save_account_chat()

    def send_chat(self):
        if self.chat_busy:
            return
        prompt = self.chat_input.get('1.0', 'end').strip()
        if not prompt:
            return
        if len(prompt) > 30000:
            self.error('Tin nhắn tối đa 30.000 ký tự'); return
        if not getattr(self, 'chat_session_id', None):
            try: self.chat_session_id = json.loads((ROOT / 'data' / 'desktop_chat_session.json').read_text(encoding='utf-8'))['id']
            except (OSError, ValueError, KeyError): self.chat_session_id = uuid.uuid4().hex
            atomic_json(ROOT / 'data' / 'desktop_chat_session.json', {'id': self.chat_session_id})
        resume_only = bool(self.messages)
        messages = [{'role': 'user', 'content': prompt}]
        if hasattr(self,'chat_account'):self.chat_account.widget.setEnabled(False)
        self.chat_busy = True; self.chat_button.configure(state='disabled'); self.chat_status.set('Muse đang trả lời…')
        self.messages.append(messages[-1]); self.chat_input.delete('1.0', 'end'); self.render_chat()
        def success(data):
            reply = dict(data['message'])
            if data.get('warnings'): reply['content'] = (reply.get('content') or '') + '\n\n' + '\n'.join(data['warnings'])
            self.messages.append(reply)
            if hasattr(self,'save_account_chat'):self.save_account_chat()
            atomic_json(self.history_path, self.messages[-100:]); self.render_chat()
            if hasattr(self, 'show_chat_media'): self.show_chat_media(reply.get('media', []))
            finish()
        def finish():
            if hasattr(self,'chat_account'):self.chat_account.widget.setEnabled(True)
            self.chat_busy = False; self.chat_button.configure(state='normal'); self.chat_status.set('')
        def failure(text):
            self.messages.pop(); self.render_chat()
            if not self.chat_input.get('1.0', 'end').strip(): self.chat_input.insert('1.0', prompt)
            finish(); self.error(text)
        chat_timeout = max(1, int(self.env.get('MUSE2API_CHAT_TIMEOUT', '600')))
        self.dispatch(lambda: self.api.call('/v1/studio/chat', {'session_id': self.chat_session_id, 'account_id':(getattr(self,'chat_account',None).get() or None) if hasattr(self,'chat_account') else None, 'prompt': prompt, 'resume_only': resume_only}, timeout=2 * chat_timeout + 120), success, failure)

    def media_controls(self, parent):
        row = ttk.Frame(parent); row.pack(fill='x', pady=(0, 8))
        kind = tk.StringVar(value='video'); size = tk.StringVar(value='1280x720'); duration = tk.IntVar(value=10)
        ttk.Label(row, text='Loại').pack(side='left'); ttk.Combobox(row, textvariable=kind, values=['image', 'video'], state='readonly', width=8).pack(side='left', padx=5)
        ttk.Label(row, text='Kích thước').pack(side='left'); ttk.Combobox(row, textvariable=size, values=['1024x1024', '1280x720', '720x1280', '1080x1920'], state='readonly', width=13).pack(side='left', padx=5)
        ttk.Label(row, text='Video (giây)').pack(side='left'); ttk.Spinbox(row, from_=1, to=10, textvariable=duration, width=5).pack(side='left', padx=5)
        return kind, size, duration

    def build_media(self):
        self.kind, self.size, self.duration = self.media_controls(self.media_tab)
        ttk.Label(self.media_tab, text='Prompt — mô tả cách dùng từng ảnh nếu có ảnh mẫu').pack(anchor='w')
        self.prompt = tk.Text(self.media_tab, height=5, wrap='word'); self.prompt.pack(fill='x', pady=6)
        self.references = ReferenceList(self.media_tab); self.references.pack(fill='x', pady=6)
        row = ttk.Frame(self.media_tab); row.pack(fill='x', pady=6)
        self.media_button = ttk.Button(row, text='Tạo ảnh / video', command=self.create_media); self.media_button.pack(side='left')
        self.media_status = tk.StringVar(); ttk.Label(row, textvariable=self.media_status).pack(side='left', padx=10)
        self.media_results = ttk.Treeview(self.media_tab, columns=('kind', 'status', 'file'), show='headings', height=7)
        for col, label in [('kind', 'Loại'), ('status', 'Trạng thái'), ('file', 'Tệp kết quả')]:
            self.media_results.heading(col, text=label)
        self.media_results.pack(fill='both', expand=True)
        actions = ttk.Frame(self.media_tab); actions.pack(fill='x', pady=6)
        ttk.Button(actions, text='Mở kết quả chọn', command=lambda: self.open_result(self.media_results)).pack(side='left')
        ttk.Button(actions, text='Lưu kết quả chọn…', command=lambda: self.save_result(self.media_results)).pack(side='left', padx=8)

    def generation_options(self, prefix):
        mode = getattr(self, prefix+'_generation_mode', None)
        language = getattr(self, prefix+'_prompt_language', None)
        notes = getattr(self, prefix+'_continuity_notes', None)
        account=getattr(self,prefix+'_account',None)
        result = {'account_id':(account.get() or None) if account else None, 'generation_mode': mode.get() if mode else 'independent',
                  'prompt_language': language.get() if language else 'auto',
                  'continuity_notes': notes.get('1.0','end').strip() if notes else ''}
        if prefix=='media' and result['generation_mode']=='coherent':
            # Each account owns its own sequence; another account may run concurrently.
            key=result['account_id'] or 'auto'
            if hasattr(self,'sequence_accounts'):
                self.generation_sequence_id=self.sequence_accounts.setdefault(key,uuid.uuid4().hex)
                atomic_json(ROOT/'data'/'desktop_sequence_accounts.json',self.sequence_accounts)
            if not getattr(self,'generation_sequence_id',None):
                try: self.generation_sequence_id=json.loads((ROOT/'data'/'desktop_generation_sequence.json').read_text(encoding='utf-8'))['id']
                except (OSError,ValueError,KeyError): self.generation_sequence_id=uuid.uuid4().hex
                atomic_json(ROOT/'data'/'desktop_generation_sequence.json',{'id':self.generation_sequence_id})
            result['sequence_id']=self.generation_sequence_id
        return result

    def new_generation_sequence(self):
        if self.active_media:
            self.error('Chờ tác vụ tạo từng cảnh hoàn tất trước khi bắt đầu chuỗi mới'); return
        self.generation_sequence_id=uuid.uuid4().hex
        if hasattr(self,'sequence_accounts'):
            self.sequence_accounts[self.media_account.get() or 'auto']=self.generation_sequence_id
            atomic_json(ROOT/'data'/'desktop_sequence_accounts.json',self.sequence_accounts)
        atomic_json(ROOT/'data'/'desktop_generation_sequence.json',{'id':self.generation_sequence_id})
        self.media_status.set('Đã bắt đầu chuỗi mới; ảnh tham chiếu được giữ lại.')

    def create_media(self):
        prompt = self.prompt.get('1.0', 'end').strip()
        if not prompt:
            self.error('Nhập prompt trước'); return
        try:
            kind = self.kind.get()
            payload = {'prompt': prompt, 'size': self.size.get(), **self.references.payload(), **self.generation_options('media')}
            if kind == 'video':
                duration = self.duration.get()
                if not 1 <= duration <= 10:
                    raise ValueError('Video từ 1–10 giây')
                payload['duration'] = duration
        except (ValueError, tk.TclError) as exc:
            self.error(str(exc)); return
        self.media_button.configure(state='disabled'); self.media_status.set('Đang gửi…')
        def success(data):
            tid = data['id']; self.active_media[tid] = kind
            self.media_results.insert('', 'end', iid=tid, values=(kind, 'Đang tạo', ''))
            self.media_button.configure(state='normal'); self.media_status.set('Đã gửi ' + tid)
            self.poll_media(tid, kind)
        def failure(text):
            self.media_button.configure(state='normal'); self.media_status.set(text); self.error(text)
        self.dispatch(lambda: self.api.call('/v1/videos' if kind == 'video' else '/v1/images/tasks', payload), success, failure)

    def poll_media(self, tid, kind):
        if self.closing:
            return
        endpoint = ('/v1/videos/' if kind == 'video' else '/v1/images/tasks/') + tid
        def success(task):
            state = task.get('status', '')
            filename = task.get('result', {}).get('filename', '')
            self.media_results.item(tid, values=(kind, state, filename))
            if state in ('completed', 'failed'):
                self.active_media.pop(tid, None)
                if state == 'failed':
                    self.log(task.get('error') or 'Tạo media thất bại')
                else:
                    self.refresh_library()
            else:
                self.root.after(2000, lambda: self.poll_media(tid, kind))
        def failure(text):
            self.media_status.set(text)
            self.root.after(4000, lambda: self.poll_media(tid, kind))
        self.dispatch(lambda: self.api.call(endpoint), success, failure)

    def build_batch(self):
        self.batch_kind, self.batch_size, self.batch_duration = self.media_controls(self.batch_tab)
        row = ttk.Frame(self.batch_tab); row.pack(fill='x')
        ttk.Button(row, text='Nhập Excel / TXT…', command=self.import_prompts).pack(side='left')
        self.batch_split = tk.StringVar(value='Mỗi dòng một prompt')
        ttk.Combobox(row, textvariable=self.batch_split, state='readonly', values=['Mỗi dòng một prompt', 'Ngăn cách bằng dòng trống'], width=29).pack(side='left', padx=10)
        self.batch_count = tk.StringVar(value='Tối đa 500 prompt'); ttk.Label(row, textvariable=self.batch_count).pack(side='left')
        self.batch_prompts = tk.Text(self.batch_tab, height=6, wrap='word'); self.batch_prompts.pack(fill='x', pady=8)
        self.batch_refs = ReferenceList(self.batch_tab); self.batch_refs.pack(fill='x')
        ttk.Label(self.batch_tab, text='Cùng bộ ảnh mẫu được dùng cho mỗi prompt trong lô.').pack(anchor='w', pady=5)
        row = ttk.Frame(self.batch_tab); row.pack(fill='x', pady=6)
        self.batch_button = ttk.Button(row, text='Chạy danh sách', command=self.create_batch); self.batch_button.pack(side='left')
        for action, label in [('pause', 'Tạm dừng'), ('resume', 'Tiếp tục'), ('stop', 'Dừng prompt chờ')]:
            ttk.Button(row, text=label, command=lambda action=action: self.control_batch(action)).pack(side='left', padx=5)
        ttk.Button(row, text='Làm mới', command=self.refresh_batches).pack(side='left', padx=5)
        self.batch_results = ttk.Treeview(self.batch_tab, columns=('kind', 'done', 'refs', 'paused'), show='tree headings', height=5)
        self.batch_results.heading('#0', text='Mã lô')
        for name, label in [('kind', 'Loại'), ('done', 'Tiến độ'), ('refs', 'Ảnh mẫu'), ('paused', 'Tạm dừng')]:
            self.batch_results.heading(name, text=label); self.batch_results.column(name, width=110)
        self.batch_results.pack(fill='both', expand=True)
        self.batch_details = tk.StringVar(); ttk.Label(self.batch_tab, textvariable=self.batch_details, wraplength=950).pack(fill='x')
        self.batch_results.bind('<<TreeviewSelect>>', lambda _: self.show_batch_details())
        self.batches = {}

    def import_prompts(self):
        raw = filedialog.askopenfilename(parent=self.root, filetypes=[('Excel / TXT', '*.xlsx *.txt')])
        if not raw:
            return
        try:
            path = Path(raw); prompts = parse_file(path.name, path.read_bytes())
            if not 1 <= len(prompts) <= 500:
                raise ValueError('File cần 1–500 prompt')
            self.batch_split.set('Ngăn cách bằng dòng trống')
            self.batch_prompts.delete('1.0', 'end'); self.batch_prompts.insert('1.0', '\n\n'.join(prompts))
            self.batch_count.set(str(len(prompts)) + ' prompt')
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def create_batch(self):
        import re
        raw = self.batch_prompts.get('1.0', 'end').strip()
        prompts = [x.strip() for x in re.split(r'\n\s*\n' if self.batch_split.get().startswith('Ngăn') else r'\n', raw) if x.strip()]
        if not 1 <= len(prompts) <= 500:
            self.error('Cần 1–500 prompt'); return
        try:
            payload = {'kind': self.batch_kind.get(), 'size': self.batch_size.get(), 'duration': self.batch_duration.get(),
                       'concurrency': 1, 'prompts': prompts, **self.batch_refs.payload(), **self.generation_options('batch')}
        except (tk.TclError, ValueError) as exc:
            self.error(str(exc)); return
        self.batch_button.configure(state='disabled')
        def finish(data):
            self.batch_button.configure(state='normal'); self.active_batches[data['id']] = True; self.refresh_batches()
        def failure(text):
            self.batch_button.configure(state='normal'); self.error(text)
        self.dispatch(lambda: self.api.call('/v1/batches', payload), finish, failure)

    def refresh_batches(self):
        def success(batches):
            selected = self.batch_results.selection()
            self.batch_results.delete(*self.batch_results.get_children()); self.batches = {b['id']: b for b in batches}
            self.active_batches.clear()
            for batch in batches:
                done = sum(x['status'] in ('completed', 'failed', 'cancelled', 'interrupted') for x in batch['items'])
                if done < len(batch['items']):
                    self.active_batches[batch['id']] = True
                self.batch_results.insert('', 'end', iid=batch['id'], text=batch['id'], values=(batch.get('account_label','Tự động')+' · '+batch['kind'], f"{done}/{len(batch['items'])}", batch.get('reference_count', 0), 'Có' if batch.get('paused') else ''))
            if selected and selected[0] in self.batches:
                self.batch_results.selection_set(selected[0])
            if self.active_batches:
                self.root.after(3500, self.refresh_batches)
        self.dispatch(lambda: self.api.call('/v1/batches'), success, lambda text: self.batch_count.set(text))

    def show_batch_details(self):
        selected = self.batch_results.selection()
        if selected:
            batch = self.batches.get(selected[0], {})
            self.batch_details.set(('Chuỗi đồng bộ nhân vật' if batch.get('generation_mode')=='coherent' else 'Tạo độc lập')+' · '+str(batch.get('prompt_language','auto'))+'\n'+str(batch.get('pause_reason',''))+'\n'+'\n'.join(f"{x['index']}. {x['status']} · {x.get('error') or x['prompt'][:70]}" for x in batch.get('items', [])[:5]))

    def control_batch(self, action):
        selected = self.batch_results.selection()
        if selected:
            self.dispatch(lambda: self.api.call('/v1/batches/' + selected[0] + '/' + action, {}), lambda _: self.refresh_batches())

    def build_library(self):
        row = ttk.Frame(self.library_tab); row.pack(fill='x', pady=6)
        ttk.Button(row, text='Làm mới thư viện', command=self.refresh_library).pack(side='left')
        ttk.Button(row, text='Mở tệp chọn', command=lambda: self.open_result(self.library)).pack(side='left', padx=8)
        ttk.Button(row, text='Lưu tệp chọn…', command=lambda: self.save_result(self.library)).pack(side='left')
        ttk.Button(row, text='Mở thư mục media', command=self.open_media_folder).pack(side='left', padx=8)
        self.library = ttk.Treeview(self.library_tab, columns=('kind', 'size', 'file'), show='headings', height=11)
        for name, label in [('kind', 'Loại'), ('size', 'Dung lượng'), ('file', 'Tên tệp')]:
            self.library.heading(name, text=label)
        self.library.pack(fill='both', expand=True)
        ttk.Label(self.library_tab, text='Tác vụ gần đây').pack(anchor='w', pady=8)
        self.task_list = ttk.Treeview(self.library_tab, columns=('kind', 'status', 'prompt'), show='headings', height=6)
        for name, label in [('kind', 'Loại'), ('status', 'Trạng thái'), ('prompt', 'Prompt')]:
            self.task_list.heading(name, text=label)
        self.task_list.pack(fill='x')

    def refresh_library(self):
        def success(data):
            media, tasks = data
            self.library.delete(*self.library.get_children())
            for item in media['media']:
                self.library.insert('', 'end', iid=item['name'], values=(item['kind'], f"{item['bytes']/1048576:.2f} MB", item['name']))
            self.task_list.delete(*self.task_list.get_children())
            for task in tasks['tasks']:
                self.task_list.insert('', 'end', values=(task['kind'], task['status'], task['prompt'][:100]))
        self.dispatch(lambda: (self.api.call('/admin/media'), self.api.call('/admin/tasks')), success)

    def result_path(self, tree):
        selected = tree.selection()
        if not selected:
            raise ValueError('Chọn một kết quả trước')
        filename = tree.item(selected[0], 'values')[-1]
        root = (ROOT / 'data' / 'media').resolve(); path = (root / filename).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError('Kết quả chưa hoàn tất hoặc không tìm thấy tệp')
        return path

    def open_result(self, tree):
        try:
            path = self.result_path(tree)
            os.startfile(str(path)) if os.name == 'nt' else webbrowser.open(path.as_uri())
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def open_media_folder(self):
        folder = ROOT / 'data' / 'media'
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder)) if os.name == 'nt' else webbrowser.open(folder.as_uri())

    def save_result(self, tree):
        try:
            path = self.result_path(tree)
            target = filedialog.asksaveasfilename(parent=self.root, initialfile=path.name, defaultextension=path.suffix)
            if target and Path(target).resolve() != path.resolve():
                shutil.copy2(path, target)
                self.log('Đã lưu kết quả: ' + target)
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def build_accounts(self):
        self.accounts = ttk.Treeview(self.accounts_tab, columns=('label', 'ok', 'enabled', 'note'), show='headings', height=10)
        for name, label in [('label', 'Tên'), ('ok', 'Phiên'), ('enabled', 'Bật'), ('note', 'Ghi chú')]:
            self.accounts.heading(name, text=label)
        self.accounts.pack(fill='both', expand=True)
        row = ttk.Frame(self.accounts_tab); row.pack(fill='x', pady=8)
        ttk.Button(row, text='Làm mới', command=self.refresh_accounts).pack(side='left')
        ttk.Button(row, text='Kiểm tra', command=lambda: self.account_action('test')).pack(side='left', padx=6)
        ttk.Button(row, text='Làm mới phiên', command=lambda: self.account_action('keepalive')).pack(side='left')
        ttk.Button(row, text='Bật / Tắt', command=self.toggle_account).pack(side='left', padx=6)
        ttk.Button(row, text='Đổi tên', command=self.rename_account).pack(side='left')
        ttk.Label(self.accounts_tab, text='Thêm / cập nhật tài khoản: mỗi dòng “tên | Cookie”, hoặc dán một Cookie').pack(anchor='w')
        self.cookie_input = tk.Text(self.accounts_tab, height=5, wrap='word'); self.cookie_input.pack(fill='x', pady=6)
        ttk.Button(self.accounts_tab, text='Nhập Cookie', command=self.add_accounts).pack(anchor='w')
        self.account_data = {}

    def refresh_accounts(self):
        def success(data):
            self.accounts.delete(*self.accounts.get_children()); self.account_data = {a['id']: a for a in data['accounts']}
            if hasattr(self,'update_account_choices'):self.update_account_choices(data['accounts'])
            for a in data['accounts']:
                self.accounts.insert('', 'end', iid=a['id'], values=(a['label'], 'Sẵn sàng' if a.get('ok') else 'Chưa xác minh', 'Có' if a.get('enabled') else 'Không', a.get('note', '')))
        self.dispatch(lambda: self.api.call('/admin/accounts'), success)

    def account_action(self, action):
        selected = self.accounts.selection()
        if selected:
            self.dispatch(lambda: self.api.call('/admin/accounts/' + selected[0] + '/' + action, {}, timeout=180), lambda _: self.refresh_accounts())

    def toggle_account(self):
        selected = self.accounts.selection()
        if selected:
            aid = selected[0]; enabled = not self.account_data[aid].get('enabled', True)
            self.dispatch(lambda: self.api.call('/admin/accounts/' + aid, {'enabled': enabled}, method='PATCH'), lambda _: self.refresh_accounts())

    def rename_account(self):
        selected = self.accounts.selection()
        if selected:
            aid = selected[0]
            name = simpledialog.askstring('Tên tài khoản', 'Tên mới:', initialvalue=self.account_data[aid]['label'], parent=self.root)
            if name:
                self.dispatch(lambda: self.api.call('/admin/accounts/' + aid, {'label': name}, method='PATCH'), lambda _: self.refresh_accounts())

    def add_accounts(self):
        value = self.cookie_input.get('1.0', 'end').strip()
        if not value:
            return
        payload = {'batch': value} if '\n' in value or '|' in value else {'cookie_header': value}
        def success(data):
            self.cookie_input.delete('1.0', 'end'); self.refresh_accounts()
            if data.get('warning'):
                messagebox.showwarning('Tài khoản', data['warning'], parent=self.root)
        self.dispatch(lambda: self.api.call('/admin/accounts', payload), success)

    def build_settings(self):
        downloads = ttk.LabelFrame(self.settings_tab, text='Tải tự động', padding=12); downloads.pack(fill='x', pady=5)
        self.auto_download = tk.BooleanVar(); self.download_folder = tk.StringVar()
        ttk.Checkbutton(downloads, text='Tự lưu ảnh / video hoàn tất', variable=self.auto_download).pack(anchor='w')
        row = ttk.Frame(downloads); row.pack(fill='x', pady=8)
        ttk.Entry(row, textvariable=self.download_folder).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Chọn thư mục…', command=self.choose_download).pack(side='left', padx=6)
        ttk.Button(row, text='Lưu', command=self.save_downloads).pack(side='left')
        telegram = ttk.LabelFrame(self.settings_tab, text='Bot Telegram — chỉ nhận lệnh từ User ID được cho phép', padding=12); telegram.pack(fill='x', pady=10)
        self.telegram_enabled = tk.BooleanVar(); self.telegram_original = tk.BooleanVar(value=True)
        self.telegram_token = tk.StringVar(); self.telegram_ids = tk.StringVar()
        ttk.Checkbutton(telegram, text='Bật bot cùng dịch vụ', variable=self.telegram_enabled).pack(anchor='w')
        ttk.Label(telegram, text='Bot token (để trống để giữ token đã lưu)').pack(anchor='w', pady=(8, 0))
        ttk.Entry(telegram, textvariable=self.telegram_token, show='•').pack(fill='x')
        ttk.Label(telegram, text='Telegram User ID, ngăn cách bằng dấu phẩy').pack(anchor='w', pady=(8, 0))
        ttk.Entry(telegram, textvariable=self.telegram_ids).pack(fill='x')
        ttk.Checkbutton(telegram, text='Giữ ảnh gốc để tải và đăng (gửi một tệp)', variable=self.telegram_original).pack(anchor='w', pady=8)
        row = ttk.Frame(telegram); row.pack(fill='x')
        ttk.Button(row, text='Lưu Telegram', command=self.save_telegram).pack(side='left')
        ttk.Button(row, text='Xem trạng thái', command=self.load_settings).pack(side='left', padx=8)
        self.telegram_status = tk.StringVar(); ttk.Label(telegram, textvariable=self.telegram_status, wraplength=970).pack(fill='x', pady=8)
        ttk.Label(telegram, text='Trong Telegram: /start → chọn Tạo ảnh / Tạo video → gửi prompt, gửi ảnh (hoặc album), chọn vai trò → Tạo / Gửi. Chat gửi trực tiếp.\n/role 1 character · /ratio 9:16 · /duration 10 · /remove 1 · /clearphotos · /last\nMáy và dịch vụ cần đang chạy để bot hoạt động.', wraplength=970).pack(fill='x')
        ttk.Button(self.settings_tab, text='Sao chép API key', command=self.copy_key).pack(anchor='w', pady=10)
        config = TelegramSettings(ROOT / 'data').public()
        self.show_telegram(config)

    def show_telegram(self, data):
        self.telegram_enabled.set(data.get('enabled', False)); self.telegram_original.set(data.get('send_original', True))
        self.telegram_ids.set(', '.join(str(x) for x in data.get('user_ids', [])))
        self.telegram_token.set('')
        self.telegram_status.set(('Bot đã kết nối: @' + data.get('username', '') if data.get('connected') else 'Bot chưa kết nối') +
                                 (' · Đã lưu token' if data.get('token_set') else ' · Chưa có token') + (' · ' + data['error'] if data.get('error') else ''))
        if data.get('restart_required'):
            self.telegram_status.set('Đã đọc/lưu cấu hình trên máy. Phiên dịch vụ cũ chưa có API Telegram — khởi động lại dịch vụ để kích hoạt bot.')

    def load_settings(self):
        def success(data):
            downloads, telegram = data
            self.auto_download.set(downloads['enabled']); self.download_folder.set(downloads['folder']); self.show_telegram(telegram)
            self.refresh_batches()
        def read():
            downloads = self.api.call('/v1/download-settings')
            try:
                telegram = self.api.call('/v1/telegram/settings')
            except LocalAPIError as exc:
                if exc.status != 404:
                    raise
                telegram = {**TelegramSettings(ROOT / 'data').public(), 'restart_required': True}
            return downloads, telegram
        self.dispatch(read, success)

    def choose_download(self):
        path = filedialog.askdirectory(parent=self.root, initialdir=self.download_folder.get() or str(Path.home()))
        if path:
            self.download_folder.set(path)

    def save_downloads(self):
        payload = {'enabled': self.auto_download.get(), 'folder': self.download_folder.get()}
        self.dispatch(lambda: self.api.call('/v1/download-settings', payload), lambda _: self.log('Đã lưu cài đặt tải tự động'))

    def save_telegram(self):
        payload = {'enabled': self.telegram_enabled.get(), 'token': self.telegram_token.get(),
                   'user_ids': self.telegram_ids.get(), 'send_original': self.telegram_original.get()}
        if self.ready:
            def save():
                try:
                    # Discover the endpoint without transmitting a new token to
                    # an outdated API. Auth errors must still stop the save.
                    self.api.call('/v1/telegram/settings')
                    return self.api.call('/v1/telegram/settings', payload, timeout=40)
                except LocalAPIError as exc:
                    if exc.status != 404:
                        raise
                    settings = TelegramSettings(ROOT / 'data')
                    settings.update(payload)
                    return {**settings.public(), 'restart_required': True}
            self.dispatch(save, self.show_telegram)
        else:
            try:
                settings = TelegramSettings(ROOT / 'data'); settings.update(payload); self.show_telegram(settings.public())
                self.telegram_status.set('Đã lưu cấu hình. Bấm Chạy dịch vụ để kích hoạt bot.')
            except ValueError as exc:
                self.error(str(exc))

    def copy_key(self):
        self.root.clipboard_clear(); self.root.clipboard_append(self.api.key); self.log('Đã sao chép API key')

    def close(self):
        owned = self.process and self.process.poll() is None
        if owned and not messagebox.askyesno('Đóng Studio', 'Đóng GUI sẽ dừng dịch vụ và bot do GUI mở. Tác vụ đang chạy có thể bị gián đoạn. Đóng?', parent=self.root):
            return
        self.closing = True
        if owned:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.log_handle:
            self.log_handle.close()
        self.root.destroy()


def main():
    lifetime_job = contain_console_processes()
    root = tk.Tk()
    app = DesktopStudio(root)
    root.mainloop()


if __name__ == '__main__':
    main()
