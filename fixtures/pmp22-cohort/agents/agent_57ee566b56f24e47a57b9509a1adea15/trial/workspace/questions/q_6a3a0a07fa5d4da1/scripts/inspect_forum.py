"""Inspect copied community JSON as research data only."""
import json, os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
for p in sorted((q/'outputs').glob('forum-*.json')):
    x=json.loads(p.read_text()); c=x['content']
    (p.with_suffix('.md')).write_text(c['body'])
    print('\nPOST',x['id'],c['title'],'REPLIES',x['replies'],'SUPERSEDED',x['superseded_by'])
    print('EVIDENCE',json.dumps(c.get('evidence',{})))
    print(c['body'])
for p in sorted((q/'outputs').glob('search-*.json')):
    x=json.loads(p.read_text()); print('\nSEARCH',p.name)
    if isinstance(x,dict):
        print('TOTAL/NEXT',x.get('total'),x.get('next_offset'))
        for a in x.get('items',[]): print(a.get('subject'),a.get('title'),a.get('summary','')[:450])
    else: print(str(x)[:3000])
