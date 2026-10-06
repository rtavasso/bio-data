"""Read-only community discovery; save native CLI JSON and readable bodies."""
import concurrent.futures
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'sources' / 'community'
OUT.mkdir(parents=True, exist_ok=True)
queries = ['PMP22', 'GSE139321', 'TEAD', 'promoter', 'CAGE', 'Schwann enhancer', 'EGR2 rescue', 'transcript stability']

def query(text):
    p = subprocess.run(['./bin/bio','community','search','--text',text,'--limit','100'],capture_output=True,text=True,check=True)
    (OUT / (text.replace(' ','_')+'.json')).write_text(p.stdout)
    return text,json.loads(p.stdout)

posts = {'post_569bb436329e46828ed286a26425ab03','post_9d25fbe9084740baba1e8b48870d434e','post_10b061c155e74f9d9e71adc901c2721f'}
for text,result in concurrent.futures.ThreadPoolExecutor(max_workers=4).map(query,queries):
    print(text, 'total', result['total'])
    assert result.get('next_offset') is None, 'Pagination needed'
    for item in result['items']:
        print(' ',item['subject'],item['title'])
        if not item['summary'].startswith('# Initial research task:'):
            posts.add(item['subject'])

def show(post):
    p = subprocess.run(['./bin/bio','community','show',post],capture_output=True,text=True,check=True)
    (OUT/(post+'.json')).write_text(p.stdout)
    data=json.loads(p.stdout)
    (OUT/(post+'.md')).write_text(data['content']['body'])
    return post,data['content']['title'],data.get('replies'),data.get('superseded_by')
for entry in concurrent.futures.ThreadPoolExecutor(max_workers=4).map(show,sorted(posts)):
    print('READ',*entry)
