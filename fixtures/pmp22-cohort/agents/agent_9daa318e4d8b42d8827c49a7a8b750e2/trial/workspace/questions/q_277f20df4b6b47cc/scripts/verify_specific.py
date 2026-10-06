from pathlib import Path
import json,hashlib,subprocess,io,gzip
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';ROOT=Q.parents[2];r=json.loads((O/'registrations.json').read_text());checks=[];errors=[]
for name,record in r['outputs'].items():
 p=O/name;h=hashlib.sha256(p.read_bytes()).hexdigest();a=json.loads(subprocess.run([str(ROOT/'bin/bio'),'artifact','show',record['artifact']],text=True,capture_output=True,check=True).stdout);ok=h==a['output_blob'] and any(x['question_id']==Q.name for x in a['questions']);checks.append({'file':str(p.relative_to(Q)),'artifact':record['artifact'],'sha256':h,'valid_hash_and_question_link':ok})
 if not ok:errors.append(name+' artifact mismatch')
for n,h in [('prediction-r001.json','8a1f87bdfed16a43d6c8fda0f1d90219cd0efbd48087ed3aae0aae138e09ee95'),('prediction-r002.json','59fd5240b9e676b0d0eed97a0c42d41eca7d2645e9e3a368328ab2b8980f1c18')]:
 if hashlib.sha256((O/n).read_bytes()).hexdigest()!=h:errors.append(n+' lock altered')
# Independently recompute primary raw contrasts from original matrix and source mapping.
D=Q/'inputs/specific';text=gzip.open(D/'GSE76027_series_matrix.txt.gz','rt').read();matrix=pd.read_csv(io.StringIO(text.split('!series_matrix_table_begin\n')[1].split('!series_matrix_table_end')[0]),sep='\t',index_col=0);mapping=pd.read_csv(O/'validation-array-mapping.tsv',sep='\t');symbols=mapping.set_index('ID').symbol;F=matrix.assign(symbol=matrix.index.map(symbols)).dropna(subset=['symbol']).groupby('symbol').median(numeric_only=True);markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];change=F.iloc[:,:3].mean(1)-F.iloc[:,3:].mean(1);lock=json.loads((O/'prediction-r002.json').read_text());models=json.loads(lock['prediction'])['frozen_models'];b=json.loads(lock['baseline_model'])['coefficients'][1];v=pd.read_csv(O/'validation-primary-results.tsv',sep='\t').set_index('candidate')
for model in models:
 g=model['gene'];base=b*change.loc[markers].mean();aug=model['myelin_beta']*change.loc[markers].mean()+model['gene_beta']*change[g];ratio=((change.Pmp22-aug)/(change.Pmp22-base))**2
 if not np.isclose(ratio,v.loc[g,'SSE_ratio'],rtol=1e-10):errors.append(g+' primary numerical mismatch')
# Current machine-readable records strict JSON, no NaN or infinity tokens.
for p in list(O.glob('*.json'))+[Q/'outputs'/n for n in ['discoveries.json','mechanisms.json','investigations.json']]:
 try:json.loads(p.read_text(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
 except Exception as e:errors.append(str(p.relative_to(Q))+': '+str(e))
# Final validation source semantics: all three HIDATA Mpz values explicitly unavailable.
H=pd.read_csv(O/'hdac3-eligible-FPKM.tsv',sep='\t',index_col=0)
if not H.loc['Mpz',['cnp-ctrl','cnp-ko','dhh-ctrl']].isna().all():errors.append('HIDATA incorrectly measured')
S=json.loads((O/'validation-summary-r003.json').read_text());assert all(x['status']=='untestable' for x in S['secondary_results'])
summary={'valid':not errors,'errors':errors,'registered_outputs_checked':len(checks),'artifacts':checks,'locks_unchanged':True,'primary_ratios_recomputed_from_source':True,'source_status_correction_applied':True,'limitations':'Validation proves file integrity, frozen arithmetic and explicit status gating, not causality, novelty, donor independence beyond source metadata or generalizability.'};(O/'verification.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in summary.items() if k!='artifacts'},indent=2));assert not errors
