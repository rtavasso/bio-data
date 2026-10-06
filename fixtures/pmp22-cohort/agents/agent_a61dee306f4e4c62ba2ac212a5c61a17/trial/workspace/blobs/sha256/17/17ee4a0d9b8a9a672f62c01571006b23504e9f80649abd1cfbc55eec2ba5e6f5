"""Verification independent of reporting logic; validate exact evidence and provenance."""
from pathlib import Path
import json,hashlib,gzip,io,datetime
import numpy as np
import pandas as pd
from openpyxl import load_workbook
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/upstream';I=Q/'inputs/upstream';root=Q.parents[2]
checks=[]
def check(name,condition,detail=None):
 assert condition,(name,detail)
 checks.append(dict(check=name,passed=True,detail=detail))
# Byte checks over every saved source attempt, including failed response bytes.
records=[json.loads(p.read_text()) for p in (I/'receipts').glob('*.json')]
for r in records:
 p=I/r['name']
 if r.get('sha256'):check('source_hash_'+r['name'],hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'])
for sf,rf in [('prediction-r001.json','prediction-seal-receipt.json'),('antioxidant-prediction-r001.json','antioxidant-seal-receipt.json')]:
 r=json.loads((O/rf).read_text());check('seal_'+sf,hashlib.sha256((O/sf).read_bytes()).hexdigest()==r['sha256'])
# Re-read all immutable RNA files and align exact native IDs to saved matrix.
saved=pd.read_csv(O/'nae1-all-expected-counts.tsv',sep='\t',index_col=0);saved.pop('symbol');rs=json.loads((I/'rna-fetch-receipts.json').read_text())
for r in rs:
 h=r['receipt']['blob'];p=root/'workspace/blobs/sha256'/h[:2]/h;check('rna_hash_'+r['name'],hashlib.sha256(p.read_bytes()).hexdigest()==h)
 d=pd.read_csv(p,compression='gzip',sep='\t',index_col=0);sample=r['name'].split('_',1)[1].split('.genes')[0]
 check('native_counts_'+sample,np.allclose(d.expected_count.reindex(saved.index),saved[sample]))
# Report values regenerated from saved full normalized matrix without importing analysis scripts.
y=pd.read_csv(O/'nae1-all-log2normalized.tsv',sep='\t',index_col=0);sym=y.pop('symbol')
positive=(saved>0).all(axis=1);geom=np.exp(np.log(saved.loc[positive]).mean(axis=1));factors=saved.loc[positive].div(geom,axis=0).median();regenerated=np.log2(saved.div(factors,axis=1)+.5)
check('all_normalized_values',np.allclose(regenerated.reindex(index=y.index,columns=y.columns),y,rtol=1e-10,atol=1e-10))
y.index=sym
wt=[s for s in y if s.startswith('WT_')];ko=[s for s in y if s.startswith('KO_')]
M=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];P=['Nqo1','Hmox1','Gclc','Gclm'];raw=saved.copy();raw.index=raw.index.str.split('_',n=1).str[1];rawlog=np.log2(raw.loc[M+['Pmp22']]+.5);rel=rawlog.loc['Pmp22']-rawlog.loc[M].mean();delta=float(rel[ko].mean()-rel[wt].mean());nae=json.loads((O/'nae1-RNA-summary.json').read_text());check('relative_effect',np.isclose(delta,nae['deltaR']),delta)
a=json.loads((O/'antioxidant-summary.json').read_text());check('locked_test_not_rescued',a['status']=='untestable' and not a['passes_locked_rule'])
el=pd.read_csv(O/'antioxidant-eligibility.tsv',sep='\t');bad=el[el.study.isin(['Nae1KO','TSC1KO','PTENKO']) & ~el.eligible];check('only_osgin1_failed_floor',set(bad.gene)=={'Osgin1'},bad.to_dict('records'))
p=json.loads((O/'antioxidant-posthoc-summary.json').read_text());score=y.loc[P].mean();effect=float(score[ko].mean()-score[wt].mean());r=next(a for a in p['panels'] if a['study']=='Nae1KO' and a['panel']=='eligible4');check('eligible_four_effect',np.isclose(effect,r['effect']),effect)
# Independently extract required native XLSX cells and verify source log2 effects.
ex=json.loads((O/'Figlia-extraction.json').read_text());wb=load_workbook(Q/ex['output'],read_only=True,data_only=False)
target=pd.read_csv(O/'antioxidant-gene-effects.tsv',sep='\t')
for group in ['TSC1KO','PTENKO','RaptorKO']:
 it=wb['Control vs '+group].iter_rows(values_only=True);headers=list(next(it));gi=headers.index('gene_name');fi=headers.index('log2 Ratio');rows=[r for r in it if r[gi] in P+M+['Pmp22']];check('native_unique_required_'+group,len(rows)==len(P+M+['Pmp22']))
 for row in rows:
  got=target[(target.study==group)&(target.gene==row[gi])].source_effect.iloc[0];check('native_effect_'+group+'_'+row[gi],np.isclose(got,row[fi]))
# No extra independent controls were introduced in four contrasts.
for r in p['panels']:check('sample_units_'+r['study']+'_'+r['panel'],r['n_control']==(4 if r['study']=='Nae1KO' else 3) and r['n_KO']==r['n_control'])
for fn in ['mechanisms.json','investigations.json','discoveries.json']:
 data=json.loads((Q/'outputs'/fn).read_text());check('JSON_'+fn,True,{'revision':data['revision']})
checks.append(dict(check='scope_limit',passed=True,detail='Structural/numerical validation is not independent biological replication or proof of causation.'))
r=dict(verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks_passed=len(checks),checks=checks)
(O/'validation.json').write_text(json.dumps(r,indent=2));print(json.dumps(dict(checks_passed=len(checks),status='PASS',relative_effect=delta,eligible4_effect=effect),indent=2))
