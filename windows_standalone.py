"""Windows installer, launcher and diagnostics for the Vietnamese community fork."""
from __future__ import annotations

import importlib.util
import os
import platform
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def contain_console_processes():
    """Keep the launcher and all future descendants in a Windows lifetime job.

    The sole job handle lives in this process (never inherited). Windows closes
    it even on console X/forced termination and kills API/Chromium descendants.
    Do not close it while the launcher is alive: it belongs to this job too.
    """
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', w.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active', w.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', w.DWORD),
                    ('scheduling', w.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = Extended()
    info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    return handle


def venv_python(root=ROOT):
    return root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def configure(root=ROOT):
    """Create a private configuration once; never overwrite existing credentials."""
    path = root / '.env'
    if not path.exists():
        text = (
            '# Cau hinh chay doc lap tren Windows. Khong chia se file nay.\n'
            f'MUSE2API_KEY=m2a_{secrets.token_urlsafe(32)}\n'
            'MUSE2API_HOST=127.0.0.1\nMUSE2API_PORT=18610\n'
            'MUSE2API_PUBLIC_BASE=\nMUSE2API_CHROMIUM=\n'
            'MUSE2API_CDP_PORT=19210\nMUSE2API_CONCURRENCY=1\n'
            'MUSE2API_IMAGE_TIMEOUT=240\nMUSE2API_VIDEO_TIMEOUT=600\n'
            'MUSE2API_CHAT_TIMEOUT=600\nMUSE2API_TOOL_PROTOCOL=0\n'
            'MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS=0\n'
            'MUSE2API_UPDATER_ENABLED=0\nMUSE2API_ALLOW_WEB_PUSH=0\n'
        )
        with path.open('x', encoding='utf-8', newline='\n') as f:
            f.write(text)
    return path


def read_env(root=ROOT):
    values = {}
    path = root / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
    return values


def local_environment(root=ROOT):
    env = dict(os.environ)
    # Explicit package values take precedence over another tool's environment.
    env.update(read_env(root))
    env['MUSE2API_HOME'] = str(root)
    env['MUSE2API_HOST'] = '127.0.0.1'
    env['MUSE2API_PROFILE_ROOT'] = str(root / 'data' / 'browser_profiles')
    env['MUSE2API_UPDATER_ENABLED'] = '0'
    env['MUSE2API_ALLOW_WEB_PUSH'] = '0'
    env['PYTHONUTF8'] = '1'
    return env


def port_is_free(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False


def get_ports(env):
    ports = [int(env.get('MUSE2API_PORT', '18610')),
             int(env.get('MUSE2API_CDP_PORT', '19210'))]
    if any(p < 1024 or p > 65535 for p in ports) or ports[0] == ports[1]:
        raise ValueError('Hai cổng phải khác nhau và nằm trong khoảng 1024–65535.')
    return ports


def detect_browser(env):
    configured = env.get('MUSE2API_CHROMIUM', '').strip()
    if configured:
        if Path(configured).is_file() or shutil.which(configured):
            return configured
        raise RuntimeError('MUSE2API_CHROMIUM không tồn tại. Sửa đường dẫn trong .env.')
    candidates = [
        Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    for name in ('chromium', 'google-chrome', 'chrome', 'msedge'):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError('Chưa tìm thấy Chrome/Edge. Cài trình duyệt hoặc đặt MUSE2API_CHROMIUM trong .env.')


def install():
    if sys.version_info < (3, 10):
        raise RuntimeError('Cần Python 3.10 trở lên; đề xuất Python 3.11.')
    print('Tạo môi trường Python riêng trong .venv...')
    python = venv_python()
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    args = [str(python), '-m', 'pip', 'install']
    wheels = ROOT / 'wheelhouse-win-py311'
    if (os.name == 'nt' and sys.version_info[:2] == (3, 11)
            and platform.machine().lower() in ('amd64', 'x86_64') and wheels.is_dir()):
        print('Cài thư viện có sẵn cho Windows/Python 3.11 64-bit...')
        args += ['--no-index', '--find-links', str(wheels)]
    else:
        print('Tải thư viện cho phiên bản Python này. Cần Internet...')
    args += ['-r', str(ROOT / 'requirements-standalone.txt')]
    subprocess.run(args,
                   cwd=ROOT, check=True)
    configure()
    print('Cài đặt xong. Chạy 02_CHAY_MUSE2API.bat. API key nằm trong .env.')


def run():
    configure()
    env = local_environment()
    if not env.get('MUSE2API_KEY'):
        raise RuntimeError('MUSE2API_KEY đang trống. Điền key riêng vào .env trước khi chạy.')
    port, cdp_port = get_ports(env)
    for p in (port, cdp_port):
        if not port_is_free(p):
            raise RuntimeError(f'Cổng {p} đang được dùng. Dừng phiên cũ hoặc đổi cổng trong .env; chương trình không dừng tiến trình khác.')
    env['MUSE2API_CHROMIUM'] = detect_browser(env)
    lifetime_job = contain_console_processes()
    url = f'http://127.0.0.1:{port}'
    print(f'Địa chỉ quản trị: {url}/admin')
    print('API key để dán vào trang quản trị: ' + env['MUSE2API_KEY'])
    print('Giữ cửa sổ này mở. Ctrl+C hoặc đóng cửa sổ sẽ dừng API và trình duyệt riêng, giải phóng cổng.')
    command = ([sys.executable, '--service-console'] if getattr(sys, 'frozen', False) else
               [sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(port)])
    child = subprocess.Popen(command, cwd=ROOT, env=env)
    try:
        deadline = time.monotonic() + 30
        ready = False
        while child.poll() is None and time.monotonic() < deadline:
            try:
                # Bypass OS proxies for the local readiness request.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(url + '/healthz', timeout=1) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.3)
        if child.poll() is not None:
            raise RuntimeError('Dịch vụ không khởi động được. Xem lỗi bên trên hoặc chạy 03_KIEM_TRA.bat.')
        if ready and '--no-browser' not in sys.argv:
            webbrowser.open(url + '/admin')
        elif not ready:
            print('Khởi động chậm. Khi dịch vụ sẵn sàng, mở địa chỉ quản trị bên trên.')
        return child.wait()
    except KeyboardInterrupt:
        print('\nĐang dừng dịch vụ...')
        # On Windows the console sends Ctrl+C to the child too. Allow the
        # application's shutdown hook to close its Chromium process first.
        try:
            child.wait(timeout=8)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            pass
        return 0
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def diagnose():
    print('Python:', sys.version.split()[0])
    print('Thư mục:', ROOT)
    for module in ('fastapi', 'uvicorn', 'pydantic', 'requests', 'websocket', 'multipart'):
        print(module + ':', 'OK' if importlib.util.find_spec(module) else 'THIẾU - chạy file cài đặt')
    env = local_environment()
    try:
        print('Trình duyệt:', detect_browser(env))
    except RuntimeError as exc:
        print(exc)
    for port in get_ports(env):
        print(f'Cổng {port}:', 'RẢNH' if port_is_free(port) else 'ĐANG DÙNG')
    print('Cấu hình .env:', 'CÓ' if (ROOT / '.env').exists() else 'CHƯA CÓ')
    print('API key:', 'ĐÃ ĐẶT' if env.get('MUSE2API_KEY') else 'CHƯA ĐẶT')
    print('Kiểm tra này không truy cập tài khoản Muse, không tạo ảnh/video và không hiển thị cookie/key.')


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    action = sys.argv[1] if len(sys.argv) > 1 else 'diagnose'
    try:
        if action == 'install':
            install()
        elif action == 'run':
            return run()
        elif action == 'diagnose':
            diagnose()
        else:
            raise ValueError('Lệnh không hợp lệ.')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('LỖI:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
