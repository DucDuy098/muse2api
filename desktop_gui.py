"""Launch the Qt desktop studio with embedded media playback."""
import sys
from windows_standalone import contain_console_processes


def main():
    try:
        from PySide6.QtWidgets import QApplication
        from qt_studio import StudioWindow, configure_application
    except ImportError:
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw()
        messagebox.showerror('Muse2API', 'Thiếu thư viện GUI. Chạy 06_CAI_GUI.bat rồi mở lại 05_MO_GUI.bat.')
        root.destroy();return 1
    lifetime_job=contain_console_processes()
    app=QApplication(sys.argv);configure_application(app)
    window=StudioWindow();window.show()
    if '--web' in sys.argv:
        import webbrowser
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, window.start_service)
        QTimer.singleShot(1500, lambda: webbrowser.open(window.api.base+'/admin'))
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
