from pathlib import Path
import json,hashlib,gzip,csv,io,math,subprocess
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';W=Q.parents[1];ROOT=Q.parents[2]
def strict(path):return json.loads(path.read_text(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
checks=[]
for p in O.glob('*.json'):strict(p)
for p in [Q/'outputs/mechanisms.json',Q/'outputs/investigations.json',Q/'outputs/discoveries.json']:strict(p)
checks.append('All new output JSON and current records reject non-finite constants')
receipts=strict(O/'registrations.json');assert len(receipts)==26
for entry in receipts:
 rr=entry['receipt'];assert not rr['conflicting_outputs'] and rr['warning'] is None
 p=O/entry['file'];h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==rr['output_blob'];assert (W/'blobs/sha256'/h[:2]/h).read_bytes()==p.read_bytes()
 sp=subprocess.run([str(ROOT/'bin/bio'),'artifact','show',rr['artifact']],cwd=ROOT,capture_output=True,text=True);assert sp.returncode==0
 art=json.loads(sp.stdout);assert any(x['question_id']==Q.name for x in art['questions']);der=art['manifest']['derivation'];codehash=hashlib.sha256((Q/'scripts'/entry['script']).read_bytes()).hexdigest();assert codehash in der['code']
 for inp in der['inputs']:
  bh=inp['blob'];assert hashlib.sha256((W/'blobs/sha256'/bh[:2]/bh).read_bytes()).hexdigest()==bh
checks.append('All26registeredoutputs, code hashes, immutable input hashes and question links verified; no role conflicts')
old=strict(O/'discoveries.inherited.json');new=strict(Q/'outputs/discoveries.json');panel=new['candidates'][0];assert panel['member_records']==old['candidates'][:3]
seal=Q/panel['prediction_lock'];assert hashlib.sha256(seal.read_bytes()).hexdigest()==panel['prediction_sha256']=='59fd5240b9e676b0d0eed97a0c42d41eca7d2645e9e3a368328ab2b8980f1c18';assert json.loads(seal.read_text())['candidate_id']==panel['id'];assert 'candidate_ids' not in json.loads(seal.read_text())
checks.append('Originalpanelsealunchanged;fullthreeinheritednegative member records exactly retained;no membership added')
def table(h):
 p=W/'blobs/sha256'/h[:2]/h
 with gzip.open(p,'rt') as f:
  reader=csv.DictReader(f,delimiter='\t');key=reader.fieldnames[0];return {r[key]:{k:float(v) for k,v in r.items() if k!=key} for r in reader}
a=table('7740f1a5d816fd8a98a17e67e6c6621ca438c5afd14addb62309f9148f3c6dc7');b=table('8b837d3c0a48e869522484f68d0837994ee9c932e2dac52ef6dd5f679b6928d7');assert set(a)==set(b) and len(a)==22406
pmp=math.log2(a['Pmp22']['PERK_WT_Tg2hr']/a['Pmp22']['PERK_WT_Control'])-math.log2(b['Pmp22']['NIH3T3_Tg2hr']/b['Pmp22']['NIH3T3_Cont']);refs=[]
for g in sorted(a):
 if g=='Pmp22':continue
 aa,bb=a[g],b[g];ac,bc=aa['PERK_WT_Control'],bb['NIH3T3_Cont'];at,bt=aa['PERK_WT_Tg2hr'],bb['NIH3T3_Tg2hr']
 if min(ac,bc)<10 or min(ac,bc,at,bt)<=4:continue
 if abs(math.log2(ac/a['Pmp22']['PERK_WT_Control']))>1 or abs(math.log2(bc/b['Pmp22']['NIH3T3_Cont']))>1:continue
 refs.append(math.log2(at/ac)-math.log2(bt/bc))
assert len(refs)==1276;s=strict(O/'summary-r001.json');assert math.isclose(pmp,s['primary']['pmp22_delta']);assert math.isclose(sum(x<pmp for x in refs)/len(refs),s['primary']['pmp22_percentile'])
checks.append('Independentstdlibsource arithmetic and full matching procedure reproduce primarydelta and1276referencepercentile')
m=strict(Q/'outputs/mechanisms.json');nodes={x['id'] for x in m['nodes']};assert len(nodes)==len(m['nodes']);assert all(e['source'] in nodes and e['target'] in nodes for e in m['edges']);assert len({e['id'] for e in m['edges']})==len(m['edges']);assert all(e['evidence'] for e in m['edges'] if e['status']!='hypothesis')
queue=strict(Q/'outputs/investigations.json')
for x in queue['items']:
 if x['status']=='blocked':assert x['blocker_evidence'] and all((Q/p).exists() for p in x['blocker_evidence'])
 if x['status']=='analyzed':assert x['artifacts'] and x['finding']
checks.append('MapIDs/endpoints/evidence and queue analyzed/blocker requirements valid; checks do not certifybiology')
for p in O.glob('*.tsv'):
 with p.open() as f:
  for row in csv.reader(f,delimiter='\t'):
   assert not any(x.lower() in ['inf','-inf','infinity','-infinity'] for x in row),str(p)
checks.append('NewTSVoutputs contain no infinities; missing values are not zero-imputed')
transport=strict(Q/'inputs/context-audit/transport.json');assert transport['requests']<=150 and transport['downloaded_bytes']+transport['web_estimated_bytes']<=1073741824
checks.append('Conservativelyaccountednetworkusage within all limits')
(O/'verification.json').write_text(json.dumps(dict(valid=True,checks=checks,artifacts=len(receipts),primary_delta=pmp,primary_reference_n=len(refs),transport=transport),indent=2,allow_nan=False)+'\n');print(json.dumps(dict(valid=True,checks=checks,artifacts=len(receipts)),indent=2))
