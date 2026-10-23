"""Short sequential media names reserved with exclusive creation across processes."""
from pathlib import Path
import re

def reserve(folder, kind, ext):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    prefix='video' if kind=='video' else 'image'
    numbers=[int(m.group(1)) for p in folder.iterdir() if (m:=re.fullmatch(prefix+r'_(\d+)\.[^.]+',p.name))]
    n=max(numbers,default=0)+1
    while True:
        target=folder/f'{prefix}_{n:03d}{ext}'
        try:return target,target.open('xb')
        except FileExistsError:n+=1
