"""Preserve exact new native bytes and authored handoff objects, sequential catalog writes."""
from pathlib import Path
import json,subprocess,hashlib
q=Path(__file__).resolve().parents[1];o=q/'outputs';root=q.parents[2];bio=str(root/'bin/bio')
reg=json.loads((o/'continuation-registration.json').read_text());known=reg.get('inputs',{})
ledger=o/'continuation-preservation.json';results=json.loads(ledger.read_text()) if ledger.exists() else {}
sources=sorted(p for p in (q/'inputs/continuation').iterdir() if p.is_file())
sources+=sorted(p for p in (o/'source-text').iterdir() if p.is_file())
authored=[q/'LABBOOK.md']+[o/n for n in ['REPORT.md','REPORT.continuation-draft.md','evidence-coverage.tsv','assay-endpoint-audit.tsv','mechanisms.json','mechanisms.r007.json','mechanisms.r008.json','investigations.json','investigations.r005.json','investigations.r006.json','continuation-registration.json','continuation-validation.json','continuation-budget.json','continuation-gap-records.json']]
for n,p in enumerate(sources+authored,1):
 key=str(p.relative_to(q));sha=hashlib.sha256(p.read_bytes()).hexdigest()
 if key in results and results[key]['sha256']==sha:continue
 old=known.get(key,{})
 if old.get('blob')==sha:
  record=old;action='existing registered input'
 else:
  args=[bio,'object','add',str(p)]
  if p in authored:args+=['--classification','interpretation']
  proc=subprocess.run(args,capture_output=True,text=True,check=True);record=json.loads(proc.stdout);assert record['blob']==sha;action='object preserved'
 results[key]={'sha256':sha,'bytes':p.stat().st_size,'action':action,'receipt':record}
 ledger.write_text(json.dumps(results,indent=2,allow_nan=False))
 if n%20==0:print('preserved',n,'of',len(sources+authored),flush=True)
print('Preserved',len(results),'paths',flush=True)
