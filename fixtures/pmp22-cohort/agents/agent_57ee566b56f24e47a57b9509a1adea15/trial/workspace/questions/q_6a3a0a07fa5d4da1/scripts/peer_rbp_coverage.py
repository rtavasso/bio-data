"""Retrospective peer-requested RBP coverage and contamination context from existing matrices.
No binding, rate, protein, mediator or cell-fraction inference.
"""
import csv,gzip,hashlib,json,os
from pathlib import Path
import numpy as np
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';WS=Q.parents[1];O=Q/'outputs'
genes=['Pmp22','Pum2','Pum1','Qki','Tia1','Igf2bp2','Snd1','Ptprc','Cx3cr1'];allrows=[];coverage=[];inputs={}
def blob(h):
    p=WS/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;inputs[h]=str(p);return p
h='7f8b8f20b3fd13166075450994acd62bf4bcbc610818f79e917a50856a4247fb'
with gzip.open(blob(h),'rt') as f:
    rd=csv.reader(f,delimiter='\t');header=next(rd);rr=list(rd)
    assert header[0]=='' and len(header)==len(rr[0])
    samples=header[1:]
fields=json.loads((O/'fields-GSE177037-full.json').read_text());meta={d['Sample_description'][0]:{'gsm':a,'title':d['Sample_title'][0]} for a,d in fields.items() if a.startswith('GSM')}
datasets=[('GSE177037',[r[0] for r in rr],np.array([[float(v) for v in r[1:]] for r in rr]),samples,meta)]
vals=[];names=None;meta={};samples=[]
fields=json.loads((O/'fields-GSE104324.json').read_text());assets=json.loads((O/'list-GSE104324.json').read_text())['items']
for arm in ['control','treated']:
    for i in [1,2,3]:
        rec=json.loads((O/f'fetch-NRG1-{arm}{i}.json').read_text());a=next(a for a in assets if a['asset_revision']==rec['previous_revision']);gsm=a['name'].split('_')[0]
        with gzip.open(blob(rec['blob']),'rt') as f:rr=[r for r in csv.reader(f,delimiter='\t') if r and not r[0].startswith('__')]
        if names is None:names=[r[0] for r in rr]
        assert names==[r[0] for r in rr];vals.append([float(r[1]) for r in rr]);samples.append(gsm);meta[gsm]={'gsm':gsm,'title':fields[gsm]['Sample_title'][0]}
datasets.append(('GSE104324',names,np.array(vals).T,samples,meta))
for ds,names,counts,samples,meta in datasets:
    assert len(names)==len(set(names)) and counts.shape==(len(names),len(samples)) and set(samples)==set(meta)
    norm=counts/counts.sum(axis=0)*1e6
    for g in genes:
        found=g in names;ix=names.index(g) if found else None
        coverage.append({'dataset':ds,'gene_requested':g,'native_exact_symbol_present':found,'alternative_Qk_prefix_tokens_not_mapped':[s for s in names if s.startswith('Qk')] if g=='Qki' and not found else [],'minimum_cpm':float(norm[ix].min()) if found else None,'maximum_cpm':float(norm[ix].max()) if found else None,'sample_count':len(samples)})
        for j,s in enumerate(samples):allrows.append({'dataset':ds,'native_sample':s,'accession':meta[s]['gsm'],'source_title':meta[s]['title'],'gene_requested':g,'status':'measured' if found else 'native_exact_symbol_unmapped','native_count':float(counts[ix,j]) if found else None,'cpm':float(norm[ix,j]) if found else None,'biological_unit':'pooled recovered O4 cells or whole nerves; donor membership unknown' if ds=='GSE177037' else 'adult rat culture experiment; donor/split mapping unresolved'})
with (O/'rbp-coverage-samples.tsv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(allrows[0]),delimiter='\t');w.writeheader();w.writerows(allrows)
(O/'rbp-coverage-summary.json').write_text(json.dumps({'stage':'retrospective peer transfer-eligibility/contamination check, not locked panel','requested_by':'post_ea149c14537c4962b6c42c404bbaf980','inputs':inputs,'coverage':coverage},indent=2,allow_nan=False))
for r in coverage:print(r)
