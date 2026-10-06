"""Inspect BioStudies file inventory and native probe annotation without target values."""
import json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
for study in ['E-MEXP-3491','E-MTAB-5633']:
    obj=json.loads((q/f'inputs/public/{study}.biostudies.json').read_text());print('\nSTUDY',study,'KEYS',list(obj))
    def walk(x):
        if isinstance(x,dict):
            if 'path' in x:print('FILE',x)
            for k,v in x.items():
                if k in ['httpLink','ftpLink','relPath','rootPath']:print('LOCATION',k,v)
                if isinstance(v,(list,dict)):walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(obj)
with (q/'inputs/public/GPL7294-full.txt').open() as f:
    for line in f:
        if line.startswith('#') or line.startswith('!platform_table_begin'):
            print(line.strip())
        if line.startswith('!platform_table_begin'):
            print('PLATFORM_COLUMNS',next(f).strip());print('PLATFORM_FIRST',next(f).strip());break
