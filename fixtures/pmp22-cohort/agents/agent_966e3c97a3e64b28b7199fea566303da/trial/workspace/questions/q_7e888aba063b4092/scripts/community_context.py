"""Save actual community queries; print compact records, never execute peer code."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'inputs'/'community'
DEST.mkdir(parents=True, exist_ok=True)
mode = sys.argv[1]
for term in sys.argv[2:]:
    command = ['./bin/bio','community',mode]
    command += ['--text',term,'--limit','100'] if mode == 'search' else [term]
    p = subprocess.run(command,capture_output=True,text=True,check=True)
    obj = json.loads(p.stdout)
    (DEST/(mode+'-'+term.replace(' ','_')+'.json')).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    if mode == 'search':
        print(term, 'total',obj['total'],'next',obj['next_offset'])
        for x in obj['items']:
            print(x['subject'], x['title'], 'superseded',x['superseded_by'])
    else:
        print(obj['id'],obj['content']['body'], '\nEVIDENCE',json.dumps(obj['content'].get('evidence',{})), '\nREPLIES', obj.get('replies'), '\nSUPERSEDED',obj.get('superseded_by'))
