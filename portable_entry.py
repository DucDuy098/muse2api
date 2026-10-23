"""Portable executable dispatcher; credentials and data always stay beside EXE."""
import os
import sys
import json
import traceback
from pathlib import Path


def enable_console():
    """Attach the BAT's CMD console even though the EXE uses a GUI bootloader."""
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    if not kernel.AttachConsole(0xFFFFFFFF) and not kernel.GetConsoleWindow():
        if not kernel.AllocConsole():
            raise ctypes.WinError(ctypes.get_last_error())
    kernel.SetConsoleOutputCP(65001)
    kernel.SetConsoleCP(65001)
    kernel.SetConsoleTitleW('Muse2API · Web / API')
    sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
    sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
    sys.stdin = open('CONIN$', 'r', encoding='utf-8')
    qa_dir = os.environ.get('MUSE2API_CONSOLE_QA_DIR')
    if qa_dir:
        # Test-only state, never console contents or credentials.
        report = {'console_attached': bool(kernel.GetConsoleWindow()),
                  'stdout_console': sys.stdout.isatty(), 'stderr_console': sys.stderr.isatty()}
        (Path(qa_dir) / (sys.argv[1].lstrip('-') + '.json')).write_text(json.dumps(report), encoding='utf-8')


def main():
    from windows_standalone import ROOT, configure, local_environment, contain_console_processes
    os.chdir(ROOT)
    configure(ROOT)
    os.environ.update(local_environment(ROOT))
    action = sys.argv[1] if len(sys.argv) > 1 else '--gui'
    if action == '--configure':
        return 0
    if action == '--console':
        enable_console()
        from windows_standalone import run
        return run()
    if action == '--service-console':
        enable_console()
        from desktop_service import main as service_main
        service_main()
        return 0
    if action in ('--service', '--diagnose'):
        (ROOT / 'data').mkdir(exist_ok=True)
        filename = 'diagnostics.txt' if action == '--diagnose' else ('desktop_service.log' if action == '--service' else 'web_launcher.log')
        stream = (ROOT / 'data' / filename).open('w' if action == '--diagnose' else 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = stream
        if action == '--service':
            from desktop_service import main as service_main
            service_main()
        else:
            from windows_standalone import diagnose
            diagnose()
        return 0
    if action == '--self-test':
        # Local acceptance test of the actual frozen GUI/player and owned service.
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from qt_studio import StudioWindow, configure_application
        from qt_media import MediaViewer
        import time
        from desktop_gui_tk import LocalAPI
        job = contain_console_processes()
        app = QApplication(sys.argv); configure_application(app)
        window = StudioWindow(); window.show()
        report = {'frozen': bool(getattr(sys, 'frozen', False)), 'tabs': window.tabs.count(), 'root': str(ROOT)}
        # Run the same start path as the GUI button, without any Muse credentials.
        window.start_service()
        deadline = time.monotonic() + 30
        api = LocalAPI(local_environment(ROOT))
        while time.monotonic() < deadline:
            app.processEvents()
            try:
                report['health'] = api.call('/healthz', timeout=1)
                report['telegram_settings'] = api.call('/v1/telegram/settings')
                report['admin_served'] = api.opener.open(api.base + '/admin', timeout=2).status == 200
                break
            except Exception:
                time.sleep(.1)
        assert 'health' in report, 'Frozen API service failed to start'
        assert report['tabs'] == 7
        window.grab().save(str(ROOT / 'data' / 'portable_gui.png'))
        sample = os.environ.get('MUSE2API_QA_VIDEO')
        if sample:
            viewer = MediaViewer(); viewer.show(); viewer.load(Path(sample), autoplay=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                app.processEvents(); time.sleep(.02)
                if viewer.player.position() > 200 and viewer.player.duration() > 0:
                    report['video_duration_ms'] = viewer.player.duration()
                    report['video_position_ms'] = viewer.player.position()
                    break
            assert 'video_duration_ms' in report, 'Frozen multimedia decoder failed'
            viewer.player.stop();viewer.close()
        window.chat_busy=False;window.active_media={};window.active_batches={};window.closing=True
        window.close();app.processEvents()
        from windows_standalone import port_is_free, get_ports
        for _ in range(100):
            if all(port_is_free(p) for p in get_ports(window.env)):break
            time.sleep(.1)
        report['ports_released'] = all(port_is_free(p) for p in get_ports(window.env))
        assert report['ports_released']
        (ROOT / 'data' / 'portable_self_test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    if action not in ('--gui', '--web'):
        raise ValueError('Tham số không hợp lệ')
    from desktop_gui import main as gui_main
    return gui_main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        from windows_standalone import ROOT
        path = ROOT / 'data' / 'portable_error.log'
        path.parent.mkdir(exist_ok=True)
        path.write_text(traceback.format_exc(), encoding='utf-8')
        if '--self-test' not in sys.argv and '--service' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'Không khởi động được. Xem data/portable_error.log.', 'Muse2API', 0x10)
        raise SystemExit(1)
