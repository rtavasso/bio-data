from pathlib import Path
import json
Q=Path(__file__).resolve().parents[1];O=Q/'outputs';I=Q/'inputs/upstream'
for fn in ['mechanisms.json','investigations.json','discoveries.json']:
 d=json.loads((O/fn).read_text());print(fn,'revision',d['revision'],'keys',list(d))
 if fn=='mechanisms.json':
  print('nodes',[(a['id'],a['label']) for a in d['nodes']]);print('last edges',json.dumps(d['edges'][-5:],indent=2));print('frontier',json.dumps(d['frontier'],indent=2))
 if fn=='investigations.json':print('pending',json.dumps([a for a in d['items'] if a['status'] not in ['analyzed','rejected','blocked']],indent=2));print('existing transport',d.get('retrieval_accounting','unset'))
p=I/'PMC6944556-BioC.json'
try:
 d=json.loads(p.read_text());passages=[p for c in d for doc in c.get('documents',[]) for p in doc.get('passages',[])];txt='\n'.join(p['text'] for p in passages if 'text' in p);(O/'upstream/PMC6944556-BioC-text.txt').write_text(txt)
 print('BIOC',len(txt))
 for s in txt.splitlines():
  if any(t in s.lower() for t in ['pmp22','nrf2','nfe2l2','nqo1']):print(s[:5000])
except Exception as e:print('BIOC unavailable',repr(e))
