from pathlib import Path
import json,subprocess,hashlib,datetime
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2];O=Q/'outputs/context-audit';receipts={}
def add(p,classification):
 r=subprocess.run([str(ROOT/'bin/bio'),'object','add',str(p),'--classification',classification],cwd=ROOT,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 receipts[str(p.relative_to(Q))]=json.loads(r.stdout)
# Preserve all acquired source bytes, error bodies and transport/discovery receipts; no source execution.
for p in sorted((Q/'inputs/context-audit').iterdir()):
 if p.is_file():add(p,'source')
# Computed outputs already immutable through registration. Preserve interpretation/checkpoint records and logs separately.
for p in sorted(O.iterdir()):
 if p.is_file() and p.suffix in ['.md','.json','.log','.stderr'] and p.name not in ['preservation.json','preservation.log','preservation.stderr']:
  add(p,'interpretation')
for pattern in ['mechanisms.r01[5-8].json','investigations.r0[12][089].json','investigations.r02[0-3].json','discoveries.r00[4-6].json']:
 for p in (Q/'outputs').glob(pattern):add(p,'interpretation')
for n in ['mechanisms.json','investigations.json','discoveries.json','evidence-coverage.tsv']:add(Q/'outputs'/n,'interpretation')
(O/'preservation.json').write_text(json.dumps(dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),objects=receipts),indent=2)+'\n')
with (Q/'LABBOOK.md').open('a') as f:
 f.write('\n### Final context-audit preserved snapshots\n')
 for n in ['outputs/mechanisms.r018.json','outputs/investigations.r023.json','outputs/discoveries.r006.json','outputs/context-audit/REPORT.md','outputs/context-audit/novelty-audit.json','outputs/evidence-coverage.tsv']:
  f.write(f'- {n}: {receipts[n]["blob"]}\n')
 f.write('All preservation receipts are in outputs/context-audit/preservation.json. Current prediction-link and status checkers pass; earlier failures remain preserved.\n')
print(json.dumps(dict(objects=len(receipts),report=receipts['outputs/context-audit/REPORT.md']['blob'])))
