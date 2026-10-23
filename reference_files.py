"""Validated named document attachments; uploaded as files, never executed locally."""
import base64
import binascii
from pathlib import Path

MIMES = {'.md': 'text/markdown', '.txt': 'text/plain', '.csv': 'text/csv',
         '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         '.xls': 'application/vnd.ms-excel', '.pdf': 'application/pdf',
         '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}

def validate_files(files):
    if not isinstance(files, list) or len(files) > 8:
        raise ValueError('Tối đa 8 tệp tài liệu')
    total = 0
    for item in files:
        if not isinstance(item, dict): raise ValueError('Tệp đính kèm không hợp lệ')
        name, value = item.get('name'), item.get('data')
        if not isinstance(name, str) or not name or len(name)>180 or '/' in name or '\\' in name or any(ord(c)<32 for c in name):
            raise ValueError('Tên tệp không hợp lệ')
        ext = Path(name).suffix.lower()
        if ext not in MIMES: raise ValueError('Hỗ trợ MD, TXT, CSV, XLSX, XLS, PDF, DOCX')
        if not isinstance(value, str) or len(value)>7*1024*1024: raise ValueError('Mỗi tài liệu tối đa 5 MB')
        header, sep, encoded = value.partition(',')
        if not sep or not header.startswith('data:') or not header.endswith(';base64'): raise ValueError('Tệp phải là data URL base64')
        try: data=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error): raise ValueError('Nội dung tệp base64 không hợp lệ')
        if not data or len(data)>5*1024*1024: raise ValueError('Mỗi tài liệu tối đa 5 MB')
        if ext in ('.md','.txt','.csv'):
            try: data.decode('utf-8-sig')
            except UnicodeError: raise ValueError('Tệp văn bản cần mã UTF-8')
        if ext in ('.xlsx','.docx') and not data.startswith(b'PK\x03\x04'): raise ValueError('Tệp Office không hợp lệ')
        if ext=='.pdf' and not data.startswith(b'%PDF-'): raise ValueError('Tệp PDF không hợp lệ')
        if ext=='.xls' and not data.startswith(bytes.fromhex('D0CF11E0A1B11AE1')): raise ValueError('Tệp XLS không hợp lệ')
        total+=len(data)
    if total>20*1024*1024: raise ValueError('Tổng tài liệu tối đa 20 MB')
    return files

def combine(images, files):
    validate_files(files or [])
    return ([*images] if isinstance(images,list) else [images] if images else []) + (files or []) or None

