"""Console-free API child of the desktop GUI. Its job owns Chromium descendants."""
import os
from windows_standalone import contain_console_processes


def main():
    lifetime_job = contain_console_processes()
    import uvicorn
    uvicorn.run('app:app', host='127.0.0.1', port=int(os.environ.get('MUSE2API_PORT', '18610')))


if __name__ == '__main__':
    main()
