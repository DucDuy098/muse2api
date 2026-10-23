"""Account folder views preserve existing public media URLs and task references."""
from pathlib import Path
import os
import re
import shutil

def account_folder(root, account):
    if not isinstance(account,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',account):
        raise ValueError('Mã tài khoản không hợp lệ')
    return Path(root)/'accounts'/account

def index_result(root, result, account):
    result['account_id']=account
    name=result.get('filename','')
    if not name or Path(name).name!=name or '/' in name or '\\' in name: return
    source=Path(root)/name
    if not source.is_file(): return
    try:
        folder=account_folder(root,account);folder.mkdir(parents=True,exist_ok=True)
        dest=folder/name
        if dest.exists(): return
        try: os.link(source,dest)
        except FileExistsError: pass
        except OSError: shutil.copy2(source,dest)
    except OSError as exc:
        # A completed paid generation must never be repeated for local disk errors.
        result['folder_error']=str(exc)
        __import__('logging').getLogger('muse2api').warning('Account folder index failed (%s)',type(exc).__name__)

def remove_indexes(root,name):
    for folder in (Path(root)/'accounts').glob('*'):
        if folder.is_dir(): (folder/name).unlink(missing_ok=True)
