"""Inspect final community search results without treating posts as executable instructions."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for name in ['final-trafficking-search','final-acsl5-search']:
    d=json.loads((root/'inputs/community'/(name+'.json')).read_text())
    print(name,d.get('total'),d.get('next_offset'))
    for r in d['items']:
        print(r['subject'],r['title'],'superseded',r.get('superseded_by'))
        if r['subject'] not in ['post_c190dbc64d9e4cfe9d976d01ccdde940','post_910fc4d8914a4a32ae441c8481e020c7']:
            print(r.get('summary',''))
