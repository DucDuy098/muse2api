"""Private Telegram controller. Reuses the application's chat and media task APIs.

No network is contacted until explicitly enabled with a token and user allowlist.
Incoming updates are checkpointed before execution; restart never replays generation.
"""
import asyncio
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
import uuid

import requests

from config import CFG
from video_references import validate_references, ROLES


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    tmp.replace(path)


class TelegramSettings:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'telegram_config.json'
        self.lock = threading.RLock()

    def read(self):
        result = {'enabled': False, 'token': '', 'user_ids': [], 'send_original': True}
        if self.path.exists():
            result.update(json.loads(self.path.read_text('utf-8')))
        elif os.getenv('MUSE2API_TELEGRAM_TOKEN'):
            result.update(token=os.environ['MUSE2API_TELEGRAM_TOKEN'],
                          user_ids=[int(x) for x in re.split(r'[,\s]+', os.getenv('MUSE2API_TELEGRAM_USER_IDS', '')) if x],
                          enabled=os.getenv('MUSE2API_TELEGRAM_ENABLED', '0') == '1')
        return result

    def update(self, changes):
        with self.lock:
            result = self.read()
            for name in ('enabled', 'send_original'):
                if name in changes:
                    if not isinstance(changes[name], bool):
                        raise ValueError('Cài đặt bật/tắt không hợp lệ')
                    result[name] = changes[name]
            if changes.get('clear_token'):
                result['token'] = ''
            elif changes.get('token'):
                if not isinstance(changes['token'], str):
                    raise ValueError('Token bot cần là chuỗi văn bản')
                token = changes['token'].strip()
                if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
                    raise ValueError('Token bot Telegram không đúng định dạng')
                result['token'] = token
            if 'user_ids' in changes:
                raw = changes['user_ids']
                if isinstance(raw, str):
                    raw = [x for x in re.split(r'[,\s]+', raw.strip()) if x]
                if not isinstance(raw, list):
                    raise ValueError('Nhập Telegram User ID, ngăn cách bằng dấu phẩy')
                try:
                    result['user_ids'] = sorted(set(int(x) for x in raw))
                except (ValueError, TypeError):
                    raise ValueError('User ID cần là số')
                if len(result['user_ids']) > 100 or any(x <= 0 for x in result['user_ids']):
                    raise ValueError('User ID cần là số dương, tối đa 100 người')
            if result['enabled'] and (not result['token'] or not result['user_ids']):
                raise ValueError('Cần token và ít nhất một Telegram User ID trước khi bật bot')
            atomic_json(self.path, result)
            return result

    def public(self):
        result = self.read()
        result['token_set'] = bool(result.pop('token'))
        return result


class TelegramRejected(RuntimeError):
    """Telegram explicitly rejected an upload; safe to try a file fallback."""


class TelegramAPI:
    def __init__(self, token):
        self.token = token
        self.base = 'https://api.telegram.org/bot' + token + '/'
        self.session = requests.Session()

    def call(self, method, data=None, files=None):
        try:
            if files:
                response = self.session.post(self.base + method, data=data, files=files, timeout=(10, 120))
            else:
                response = self.session.post(self.base + method, json=data or {}, timeout=(5, 15))
            result = response.json()
        except (requests.RequestException, ValueError):
            # requests exceptions contain the URL (and bot token). Never surface it.
            raise RuntimeError('Không kết nối được Telegram. Kiểm tra mạng hoặc proxy.') from None
        if not result.get('ok'):
            if result.get('error_code') in (401, 404) and method in ('getMe', 'getUpdates', 'getWebhookInfo'):
                raise RuntimeError('Telegram từ chối token: bot không tồn tại hoặc token không còn hợp lệ. Kiểm tra token từ BotFather.')
            if result.get('error_code') == 409 and method == 'getUpdates':
                raise RuntimeError('Bot Telegram đang được một phiên khác hoặc webhook sử dụng. Chỉ bật bot ở một phiên dịch vụ.')
            description = str(result.get('description', 'Telegram từ chối yêu cầu')).replace(self.token, '[token]')
            raise TelegramRejected(description)
        return result['result']

    def image(self, file_id, mime):
        info = self.call('getFile', {'file_id': file_id})
        if info.get('file_size', 0) > 5 * 1024 * 1024:
            raise ValueError('Ảnh mẫu tối đa 5 MB')
        path = info.get('file_path', '')
        if not path or '..' in path or path.startswith('/'):
            raise ValueError('Không tải được ảnh mẫu từ Telegram')
        try:
            with self.session.get('https://api.telegram.org/file/bot' + self.token + '/' + path,
                                  stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 5 * 1024 * 1024:
                        raise ValueError('Ảnh mẫu tối đa 5 MB')
        except requests.RequestException:
            raise RuntimeError('Không tải được ảnh mẫu từ Telegram') from None
        return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')


def send_alert(text: str) -> None:
    """One-off notification (account/cookie expiry etc.) — reuses the same
    bot/chat config as normal generation delivery, no separate alert channel.
    Silently no-ops if Telegram isn't configured; never raises into callers
    like the keepalive loop."""
    try:
        settings = TelegramSettings(CFG.data_dir).read()
        if not settings.get('enabled') or not settings.get('token') or not settings.get('user_ids'):
            return
        api = TelegramAPI(settings['token'])
        for uid in settings['user_ids']:
            try:
                api.call('sendMessage', {'chat_id': uid, 'text': text})
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass


MENU = {'keyboard': [['🖼 Tạo ảnh', '🎬 Tạo video', '💬 Chat Muse'],
                     ['▶️ Tạo / Gửi', '📋 Trạng thái', '🧹 Bỏ ảnh'], ['🔄 Chat mới', '❌ Hủy soạn']],
        'resize_keyboard': True}
BUTTONS = {'🖼 Tạo ảnh': '/image', '🎬 Tạo video': '/video', '💬 Chat Muse': '/chat',
           '▶️ Tạo / Gửi': '/generate', '📋 Trạng thái': '/status', '🧹 Bỏ ảnh': '/clearphotos',
           '🔄 Chat mới': '/new', '❌ Hủy soạn': '/cancel'}


class MuseBridge:
    def __init__(self, g):
        self.g = g

    def chat(self, messages):
        result = asyncio.run(self.g['chat_completions'](self.g['ChatRequest'](messages=messages, stream=False), _=None))
        return result['choices'][0]['message'].get('content') or ''

    def chat_session(self, session_id, prompt):
        from studio_chat import StudioChatRequest
        return self.g['studio_chat_reply'](StudioChatRequest(session_id=session_id, prompt=prompt))

    def submit(self, kind, prompt, images, roles, size, duration):
        request = {'prompt': prompt, 'size': size, 'reference_images': images or None, 'reference_roles': roles or None}
        if kind == 'video':
            request['duration'] = duration
            return asyncio.run(self.g['create_video'](self.g['VideoRequest'](**request), _=None))['id']
        result = self.g['create_image_task'](self.g['ImageRequest'](**request), idempotency_key=None, _=None)
        return json.loads(result.body)['id']

    def task(self, task_id):
        return self.g['store'].get_task(task_id)

    def media(self, task):
        name = task.get('result', {}).get('filename', '')
        root = Path(self.g['CFG'].media_dir).resolve()
        path = (root / name).resolve()
        if not name or path.parent != root or not path.is_file():
            raise ValueError('Không tìm thấy tệp kết quả trong thư viện')
        return path


class TelegramRuntime:
    def __init__(self, config, bridge, data_dir, api=None):
        self.config, self.bridge = config, bridge
        self.api = api or TelegramAPI(config['token'])
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.RLock()
        self.drafts, self.busy = {}, set()
        self.path = Path(data_dir) / 'telegram_state.json'
        self.state = {'offset': 0, 'bot_hash': '', 'history': {}, 'last': {}}
        if self.path.exists():
            self.state.update(json.loads(self.path.read_text('utf-8')))
        digest = hashlib.sha256(config['token'].encode()).hexdigest()
        if self.state['bot_hash'] != digest:
            self.state['offset'], self.state['bot_hash'] = 0, digest
        self.error, self.poll_error, self.username, self.connected = '', '', '', False

    def save(self):
        atomic_json(self.path, self.state)

    def say(self, chat, text, **kwargs):
        if self.stop_event.is_set():
            return
        # Telegram limits text by UTF-16 units; keep chunks below 4096.
        pieces, current, units = [], '', 0
        for char in str(text):
            n = 2 if ord(char) > 65535 else 1
            if units + n > 3500:
                pieces.append(current); current, units = '', 0
            current += char; units += n
        pieces.append(current or 'Muse không trả lời bằng văn bản.')
        for part in pieces:
            self.api.call('sendMessage', {'chat_id': chat, 'text': part, **kwargs})

    def draft(self, uid):
        return self.drafts.setdefault(uid, {'kind': 'chat', 'prompt': '', 'images': [], 'roles': [], 'size': '16:9', 'duration': 10, 'revision': 0})

    def process(self, update):
        callback = update.get('callback_query')
        msg = callback.get('message', {}) if callback else update.get('message', {})
        user = callback.get('from', {}) if callback else msg.get('from', {})
        uid, chat = user.get('id'), msg.get('chat', {}).get('id')
        if uid not in self.config['user_ids'] or msg.get('chat', {}).get('type') != 'private' or chat != uid:
            return  # reject before downloading photos, mutating state or invoking Muse
        with self.lock:
            draft = self.draft(uid)
            if callback:
                self.api.call('answerCallbackQuery', {'callback_query_id': callback['id']})
                try:
                    _, revision, index, role = callback.get('data', '').split(':')
                    index = int(index)
                    if uid in self.busy or int(revision) != draft['revision'] or role not in ROLES or not 0 <= index < len(draft['roles']):
                        raise ValueError()
                    draft['roles'][index] = role
                    self.say(chat, f'Ảnh {index + 1}: {role}')
                except (ValueError, TypeError):
                    self.say(chat, 'Bộ ảnh đã thay đổi hoặc đang tạo. Hãy dùng nút của ảnh hiện tại.')
                return
            text = BUTTONS.get(msg.get('text', ''), msg.get('text', '')).strip()
            command, _, arg = text.partition(' ')
            command = command.split('@')[0].lower()
            if command in ('/start', '/help'):
                self.say(chat, 'Chọn Chat / Tạo ảnh / Tạo video. Với ảnh hoặc video: gửi prompt và tối đa 8 ảnh (có thể gửi album), chọn vai trò rồi bấm Tạo / Gửi.\n/ratio 16:9 hoặc 9:16 hoặc 1:1; /duration 10; /role 1 character; /last gửi lại kết quả gần nhất.\n/cancel chỉ hủy bản soạn; tác vụ đã gửi vẫn chạy.', reply_markup=MENU)
                return
            if command == '/status':
                task_id = self.state['last'].get(str(uid))
                task = self.bridge.task(task_id) if task_id else None
                self.say(chat, ('Đang xử lý. ' if uid in self.busy else 'Sẵn sàng. ') +
                         (f"Tác vụ {task_id}: {task.get('status')}" if task else '') +
                         f"\nChế độ {draft['kind']}; {len(draft['images'])} ảnh; {draft['size']}; video {draft['duration']} giây.")
                return
            if uid in self.busy:
                self.say(chat, 'Yêu cầu trước đang chạy. Dùng /status để kiểm tra; chưa gửi thêm tác vụ mới.')
                return
            if command == '/last':
                task_id = self.state['last'].get(str(uid))
                task = self.bridge.task(task_id) if task_id else None
                if task and task.get('status') == 'completed':
                    self.deliver(chat, task)
                else:
                    self.say(chat, 'Chưa có kết quả hoàn tất. /last chỉ gửi lại tệp, không tạo lại.')
                return
            if command in ('/image', '/video', '/chat'):
                draft.update(kind=command[1:], prompt=arg, images=[], roles=[], revision=draft['revision'] + 1)
                self.say(chat, f"Đã chọn {draft['kind']}. " + ('Gửi tin nhắn để chat.' if command == '/chat' else 'Gửi prompt, gửi ảnh mẫu nếu cần, sau đó bấm Tạo / Gửi.'), reply_markup=MENU)
                if command == '/chat' and arg:
                    self.submit(uid, chat, arg)
                return
            if command in ('/cancel', '/clearphotos'):
                draft.update(images=[], roles=[], revision=draft['revision'] + 1)
                if command == '/cancel':
                    draft['prompt'] = ''
                self.say(chat, 'Đã bỏ ảnh và bản soạn.' if command == '/cancel' else 'Đã bỏ tất cả ảnh mẫu.')
                return
            if command == '/new':
                self.state['history'][str(uid)] = []
                self.state.setdefault('chat_sessions', {})[str(uid)] = uuid.uuid4().hex
                self.save()
                draft.update(kind='chat', prompt='', images=[], roles=[], revision=draft['revision'] + 1)
                self.say(chat, 'Đã bắt đầu chat mới.')
                return
            if command == '/ratio':
                if arg not in ('16:9', '9:16', '1:1'):
                    raise ValueError('Dùng /ratio 16:9, /ratio 9:16 hoặc /ratio 1:1')
                draft['size'] = arg
                self.say(chat, 'Tỷ lệ: ' + arg)
                return
            if command == '/duration':
                if not arg.isdigit() or not 1 <= int(arg) <= 10:
                    raise ValueError('Dùng /duration 10 (cho phép 1–10 giây)')
                draft['duration'] = int(arg)
                self.say(chat, 'Thời lượng: ' + arg + ' giây')
                return
            if command == '/role':
                parts = arg.split()
                if len(parts) != 2 or not parts[0].isdigit() or not 1 <= int(parts[0]) <= len(draft['roles']) or parts[1] not in ROLES:
                    raise ValueError('Ví dụ: /role 1 character; vai trò: reference, character, scene, background, first_frame')
                draft['roles'][int(parts[0]) - 1] = parts[1]
                self.say(chat, 'Đã đặt vai trò ảnh.')
                return
            if command == '/remove':
                if not arg.isdigit() or not 1 <= int(arg) <= len(draft['images']):
                    raise ValueError('Dùng /remove 1 để bỏ ảnh số 1')
                index = int(arg) - 1
                draft['images'].pop(index); draft['roles'].pop(index)
                draft['revision'] += 1
                self.say(chat, f"Đã bỏ ảnh {arg}. Còn {len(draft['images'])} ảnh; dùng /role để đặt lại vai trò theo số mới.")
                return
            photo, doc = msg.get('photo'), msg.get('document')
            if photo or doc:
                if draft['kind'] == 'chat':
                    raise ValueError('Chọn /image hoặc /video trước khi gửi ảnh mẫu.')
                if len(draft['images']) >= 8:
                    raise ValueError('Tối đa 8 ảnh mẫu; /clearphotos để bỏ ảnh')
                attachment = photo[-1] if photo else doc
                mime = 'image/jpeg' if photo else attachment.get('mime_type', '')
                if mime not in ('image/jpeg', 'image/png', 'image/webp'):
                    raise ValueError('Gửi ảnh PNG, JPG hoặc WEBP')
                if attachment.get('file_size', 0) > 5 * 1024 * 1024:
                    raise ValueError('Mỗi ảnh tối đa 5 MB')
                image = self.api.image(attachment['file_id'], mime)
                validate_references(draft['images'] + [image], draft['roles'] + ['reference'])
                draft['images'].append(image); draft['roles'].append('reference')
                if msg.get('caption'):
                    draft['prompt'] = msg['caption'][:30000]
                index = len(draft['images']) - 1
                names = [('reference', 'Tham khảo'), ('character', 'Nhân vật'), ('scene', 'Bối cảnh'), ('background', 'Nền'), ('first_frame', 'Khung đầu')]
                keyboard = {'inline_keyboard': [[{'text': label, 'callback_data': f"r:{draft['revision']}:{index}:{role}"} for role, label in names[:3]],
                                                [{'text': label, 'callback_data': f"r:{draft['revision']}:{index}:{role}"} for role, label in names[3:]]]}
                self.say(chat, f'Đã nhận ảnh {index + 1}. Chọn vai trò. Khi gửi đủ bộ ảnh, bấm Tạo / Gửi.', reply_markup=keyboard)
                return
            if command == '/generate':
                self.submit(uid, chat, draft['prompt'])
            elif text.startswith('/'):
                self.say(chat, 'Lệnh chưa được hỗ trợ. Dùng /help.')
            elif text:
                if len(text) > 30000:
                    raise ValueError('Prompt tối đa 30.000 ký tự')
                if draft['kind'] == 'chat':
                    self.submit(uid, chat, text)
                else:
                    draft['prompt'] = text
                    self.say(chat, f"Đã nhận prompt và {len(draft['images'])} ảnh. Gửi thêm ảnh hoặc bấm Tạo / Gửi.")

    def submit(self, uid, chat, text):
        if not text.strip():
            raise ValueError('Gửi prompt trước rồi bấm Tạo / Gửi')
        draft = dict(self.draft(uid))
        draft['images'], draft['roles'] = list(draft['images']), list(draft['roles'])
        history = list(self.state['history'].get(str(uid), []))[-20:]
        self.busy.add(uid)
        try:
            self.say(chat, 'Đã nhận yêu cầu. Đang chờ Muse…')
        except Exception:
            self.busy.discard(uid)
            raise

        def work():
            try:
                if draft['kind'] == 'chat':
                    messages = history + [{'role': 'user', 'content': text}]
                    chat_media = []
                    if hasattr(self.bridge, 'chat_session'):
                        with self.lock:
                            session_id = self.state.setdefault('chat_sessions', {}).setdefault(str(uid), uuid.uuid4().hex)
                            self.save()
                        response = self.bridge.chat_session(session_id, text)
                        answer = response['message'].get('content') or ''
                        chat_media = response['message'].get('media', [])
                        if response.get('warnings'): answer += '\n\n' + '\n'.join(response['warnings'])
                    else:
                        answer = self.bridge.chat(messages)
                    with self.lock:
                        self.state['history'][str(uid)] = (messages + [{'role': 'assistant', 'content': answer}])[-20:]
                        self.save()
                    if answer.strip(): self.say(chat, answer)
                    for item in chat_media:
                        self.deliver(chat, {'id': 'chat_' + uuid.uuid4().hex[:16], 'kind': item['kind'],
                                            'result': {'filename': item['filename']}})
                else:
                    task_id = self.bridge.submit(draft['kind'], text, draft['images'], draft['roles'], draft['size'], draft['duration'])
                    with self.lock:
                        self.state['last'][str(uid)] = task_id
                        self.save()
                    self.say(chat, 'Tác vụ ' + task_id + ' đã gửi. /status xem tiến độ.')
                    deadline = time.monotonic() + 1200
                    while not self.stop_event.wait(1):
                        task = self.bridge.task(task_id)
                        if task and task.get('status') == 'completed':
                            self.deliver(chat, task); break
                        if task and task.get('status') == 'failed':
                            raise RuntimeError(task.get('error') or 'Muse tạo media thất bại')
                        if time.monotonic() > deadline:
                            self.say(chat, 'Chưa có kết quả sau 20 phút. Dùng /status, rồi /last khi hoàn tất; không cần tạo lại.'); break
            except Exception as exc:
                self.error = self.safe_error(exc)
                try:
                    self.say(chat, 'Lỗi: ' + self.error)
                except Exception:
                    pass
            finally:
                with self.lock:
                    self.busy.discard(uid)
        threading.Thread(target=work, daemon=True, name='telegram-muse-request').start()

    def safe_error(self, exc):
        text = str(getattr(exc, 'detail', '') or exc)
        return text.replace(self.config['token'], '[token]')[:1000]

    def deliver(self, chat, task):
        if self.stop_event.is_set():
            return
        path = self.bridge.media(task)
        if path.stat().st_size > 50 * 1024 * 1024:
            self.say(chat, 'Kết quả lớn hơn 50 MB, vượt giới hạn tải lên Bot API. Tệp vẫn có trong Thư viện trên PC.')
            return
        kind = task['kind']
        method = 'sendVideo' if kind == 'video' else 'sendPhoto'
        field = 'video' if kind == 'video' else 'photo'
        if kind == 'image' and (self.config.get('send_original', True) or path.stat().st_size > 10 * 1024 * 1024):
            method, field = 'sendDocument', 'document'
        try:
            with path.open('rb') as handle:
                self.api.call(method, {'chat_id': chat, 'caption': 'Muse · ' + task['id']},
                              files={field: (path.name, handle, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')})
        except TelegramRejected:
            # Fall back only after an explicit rejection. A network timeout may
            # occur after Telegram accepted the file, so never resend on timeout.
            if method == 'sendDocument':
                raise
            with path.open('rb') as handle:
                self.api.call('sendDocument', {'chat_id': chat, 'caption': 'Tệp gốc để tải và đăng · ' + task['id']},
                              files={'document': (path.name, handle, 'application/octet-stream')})

    def run(self):
        while not self.stop_event.is_set():
            try:
                if not self.connected:
                    info = self.api.call('getMe')
                    webhook = self.api.call('getWebhookInfo')
                    if webhook.get('url'):
                        raise RuntimeError('Bot đang dùng webhook ở dịch vụ khác. Dùng một bot riêng hoặc gỡ webhook trước khi bật.')
                    self.username, self.connected = info.get('username', ''), True
                updates = self.api.call('getUpdates', {'offset': self.state['offset'], 'timeout': 8,
                                                     'allowed_updates': ['message', 'callback_query']})
                for update in updates:
                    if self.stop_event.is_set():
                        return
                    with self.lock:
                        if update['update_id'] < self.state['offset']:
                            continue
                        self.state['offset'] = update['update_id'] + 1
                        self.save()
                    try:
                        self.process(update)
                    except Exception as exc:
                        self.error = self.safe_error(exc)
                        message = update.get('message') or update.get('callback_query', {}).get('message', {})
                        chat = message.get('chat', {}).get('id')
                        if chat in self.config['user_ids'] and message.get('chat', {}).get('type') == 'private':
                            self.say(chat, 'Lỗi: ' + self.error)
                self.poll_error = ''
            except Exception as exc:
                self.poll_error = self.safe_error(exc)
                self.connected = False
                self.stop_event.wait(5)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='telegram-long-poll')
        self.thread.start()

    def stop(self):
        self.stop_event.set()


class TelegramController:
    def __init__(self, g):
        self.g, self.lock = g, threading.Lock()
        self.settings = TelegramSettings(g['CFG'].data_dir)
        self.runtime = None

    def status(self):
        runtime = self.runtime
        return {**self.settings.public(), 'running': bool(runtime and runtime.thread and runtime.thread.is_alive()),
                'connected': bool(runtime and runtime.connected), 'username': runtime.username if runtime else '',
                'error': (runtime.poll_error or runtime.error) if runtime else '', 'busy_users': len(runtime.busy) if runtime else 0}

    def reload(self):
        with self.lock:
            if self.runtime:
                self.runtime.stop()
                self.runtime.thread.join(timeout=20)
                if self.runtime.thread.is_alive():
                    raise RuntimeError('Bot cũ đang kết thúc kết nối. Chờ vài giây rồi lưu lại.')
                self.runtime = None
            config = self.settings.read()
            if config['enabled'] and config['token'] and config['user_ids']:
                self.runtime = TelegramRuntime(config, MuseBridge(self.g), self.g['CFG'].data_dir)
                self.runtime.start()

    def update(self, data):
        if self.runtime and self.runtime.busy:
            raise ValueError('Bot có yêu cầu đang chạy. Chờ hoàn tất trước khi đổi cấu hình.')
        self.settings.update(data)
        self.reload()
        return self.status()


def install(g):
    from fastapi import Depends, HTTPException, Request
    controller = TelegramController(g)
    g['_telegram_controller'] = controller
    app, auth = g['app'], g['auth']

    @app.get('/v1/telegram/settings')
    def settings(_=Depends(auth)):
        return controller.status()

    @app.post('/v1/telegram/settings')
    async def configure(request: Request, _=Depends(auth)):
        try:
            return await asyncio.to_thread(controller.update, await request.json())
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))

    # Team-RBAC wrappers for the Next.js web UI. Token/user-id config is
    # sensitive, so this needs admin (not just member).
    webauth = g['webauth']

    @app.get('/admin/telegram/settings')
    def admin_telegram_settings(user=Depends(webauth.require_role('admin'))):
        return controller.status()

    @app.post('/admin/telegram/settings')
    async def admin_telegram_configure(request: Request, user=Depends(webauth.require_role('admin'))):
        try:
            return await asyncio.to_thread(controller.update, await request.json())
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))

    @app.on_event('startup')
    def start():
        controller.reload()

    @app.on_event('shutdown')
    def stop():
        if controller.runtime:
            controller.runtime.stop()
