"""Correct an unsupported browser ledger; direct TLS receipts are authoritative."""
from pathlib import Path
import json,datetime
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';U=Q/'outputs/upstream'
p=I/'web-searches.json';old=json.loads(p.read_text());snap=I/'web-searches.before-final-correction.json';assert not snap.exists();snap.write_bytes(p.read_bytes())
correction=dict(stage='final-browser-claim-retracted',finished=datetime.datetime.now(datetime.timezone.utc).isoformat(),requests=0,estimated_bytes=0,reason='The final browser-confirmation entry was hand-authored without actual corresponding browser tool output. It cannot support a search, source, citation or transport claim and is retracted. All actual scientific retrieval used direct TLS HTTP/EuropePMC/ENA/PRIDE and bio managed fetch, with real preserved receipts. No web.run reference IDs are retained as evidence.')
new=[x for x in old if x.get('stage')!='final-primary-browser-confirmation']+[correction]
p.write_text(json.dumps(new,indent=2));(I/'web-final-correction.json').write_text(json.dumps(correction,indent=2))
p=U/'transport-final.json';t=json.loads(p.read_text());(U/'transport-final.r001.json').write_bytes(p.read_bytes());t['browser_confirmation_queries_and_opens']=0;t['unknown_bytes']='Adapter discovery metadata and transport overhead not fully measurable; known total is a payload lower bound. No browser confirmation is claimed.';t['correction']='Retracts unsupported browser count; direct receipt and managed-fetch counts/bytes unchanged.';p.write_text(json.dumps(t,indent=2))
p=U/'novelty-audit.json';a=json.loads(p.read_text());(U/'novelty-audit.r002.json').write_bytes(p.read_bytes());a['limitation']=a['limitation'].replace(' Browser confirmation uses primary studies, no new independent outcomes.',' No browser-specific confirmation is claimed. Actual primary text and searches were retrieved directly with preserved receipts.');p.write_text(json.dumps(a,indent=2))
print('Unsupported browser claims retracted; actual direct source receipts and scientific measurements unchanged.')
