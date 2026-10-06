from pathlib import Path
import json,hashlib,subprocess,gzip,io,math
import pandas as pd,numpy as np
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/iteration';W=Q.parents[1];bio=Path.cwd()/'bin/bio'
def bad(x):raise ValueError('nonfinite JSON token '+x)
json_count=0
for p in O.glob('*.json'):json.loads(p.read_text(),parse_constant=bad);json_count+=1
regs=json.loads((O/'registrations.json').read_text());checks=[];hashes=set()
for item in regs:
 r=item['receipt'];p=Q/item['file'];h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==r['output_blob'],p
 if r.get('conflicting_outputs') or r.get('warning'):
  assert item.get('superseded_for_reuse') and item.get('resolution'),r
  resolved=json.loads(subprocess.run([str(bio),'artifact','show',item['resolution']['artifact']],capture_output=True,text=True,check=True).stdout)
  assert resolved['output_blob']==h and resolved['output_role'].endswith(p.suffix.lstrip('.'))
 obj=json.loads(subprocess.run([str(bio),'artifact','show',r['artifact']],capture_output=True,text=True,check=True).stdout)
 assert any(x['question_id']==Q.name for x in obj['questions']);assert obj['output_blob']==h
 der=obj['manifest']['derivation'];hashes.add(h);hashes.update(der['code']);hashes.update(x['blob'] for x in der['inputs'])
 checks.append({'path':item['file'],'artifact':r['artifact'],'output_hash_ok':True,'question_link_ok':True,'code':der['code']})
for h in hashes:
 p=W/'blobs/sha256'/h[:2]/h;assert p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==h,h
sealed=O/'prediction-r001.json';assert hashlib.sha256(sealed.read_bytes()).hexdigest()=='ad886ca8e48a1d0db27ce28b1b189c59c1729d288602363b6149bc0524952947'
# Independent endpoint arithmetic from preserved source counts, separate implementation.
f=pd.read_csv(Q/'inputs/iteration/GSE90070_dataCount.csv.gz',index_col=0);ok=(f>0).all(axis=1);logs=np.log(f.loc[ok]);sf=np.exp(np.median(logs.to_numpy()-logs.mean(axis=1).to_numpy()[:,None],axis=0));v=np.log2(f.loc['Pmp22'].to_numpy()/sf);s=pd.read_csv(O/'isr-samples.tsv',sep='\t',index_col=0).loc[f.columns];calc={}
for c in s.condition.unique():
 for fr in ['In','H']:calc[c,fr]=v[((s.condition==c)&(s.fraction==fr)).to_numpy()].mean()
res=pd.read_csv(O/'isr-panel-effects.tsv',sep='\t');res=res[(res.gene=='Pmp22')&(res.method=='median_ratio')]
# Median of logs vs log of median differs for even feature counts. Here11817 positive genes => exact equivalence.
assert ok.sum()%2==1
for name,a,b in [('acute','Tg1','Ctrl'),('chronic_vs_acute','Tg16','Tg1'),('chronic_vs_control','Tg16','Ctrl'),('PERKi','Tg16+PERKi','Tg16')]:
 for endpoint,fr in [('cytosolic','In'),('polysome','H')]:
  expected=calc[a,fr]-calc[b,fr];observed=res[(res.contrast==name)&(res.endpoint==endpoint)].log2_effect.iloc[0];assert abs(expected-observed)<1e-10
# Frozen primary rule and native-quality invariants.
t=pd.read_csv(O/'genetic-pmp22-effects.tsv',sep='\t');assert abs(t[t.genotype=='Wild Type'].log2_effect.median()+.320443497875)<1e-10
native=pd.read_csv(O/'array-Pmp22-native-flags.tsv',sep='\t');assert len(native)==48 and native.eligible_conservative.all()
assert not json.loads((O/'genetic-validation-summary.json').read_text())['primary_pass']
for p in [Q/'outputs/mechanisms.json',Q/'outputs/investigations.json',Q/'outputs/discoveries.json']:json.loads(p.read_text(),parse_constant=bad)
ledger=json.loads((Q/'inputs/iteration/transport.json').read_text());n=len(ledger['entries'])+13;byte=sum(x.get('bytes',0) for x in ledger['entries'])+260000;assert n<=150 and byte<=1073741824;assert all(x.get('bytes',0)<=536870912 for x in ledger['entries'])
report={'json_files_checked':json_count,'registered_outputs_checked':len(regs),'unique_immutable_blobs_verified':len(hashes),'artifact_checks':checks,'sealed_prediction_unchanged':True,'Pmp22_effects_independently_recomputed':True,'native_target_rows_all_flags_pass':48,'retrieval_requests_including_web':n,'accounted_bytes_including_web_estimate':byte,'web_byte_estimate':260000,'limitations':'Integrity checks do not validate biological independence, normalize missing calibration, or certify a novel causal mechanism.'}
(O/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in report.items() if k!='artifact_checks'},indent=2))
