"""Exploratory array contrasts in source-normalized units, without inventing a log base.
Source probe annotation only; no array raw-data normalization or code execution.
"""
import csv,gzip,hashlib,json,os,re
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import t
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';P=Q/'inputs/public';O=Q/'outputs'
spec=json.loads((Q/'inputs/panel-spec.json').read_text());panels=spec['panels'];wanted=['Pmp22',*sum(panels.values(),[])];inputs={}
def source(name):
    p=P/name;r=json.loads(p.with_name(p.name+'.receipt.json').read_text())
    assert r['status']==200 and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];inputs[name]=r['sha256'];return p
def stats(a,b):
    a=np.asarray(a);b=np.asarray(b);effect=float(b.mean()-a.mean());va=a.var(ddof=1)/len(a);vb=b.var(ddof=1)/len(b);se=float(np.sqrt(va+vb))
    if se==0:return {'effect':effect,'ci_low':effect,'ci_high':effect,'df':None}
    df=float((va+vb)**2/(va*va/(len(a)-1)+vb*vb/(len(b)-1)));d=float(t.ppf(.975,df)*se)
    return {'effect':effect,'ci_low':effect-d,'ci_high':effect+d,'df':df}
# An exact manufacturer probe ID mapping from the retrieved rat Agilent platform;
# E-MEXP uses it only as an external probe annotation, not as proof of platform equivalence.
annotation=defaultdict(set)
with source('GPL7294-full.txt').open() as f:
    for line in f:
        if line.startswith('!platform_table_begin'):break
    reader=csv.DictReader(f,delimiter='\t')
    for row in reader:
        if row['ID'].startswith('!'):break
        if row['CONTROL_TYPE']=='FALSE' and row['GENE_SYMBOL']:
            annotation[row['ID']].add(row['GENE_SYMBOL'])
map_valid={p:next(iter(s)) for p,s in annotation.items() if len(s)==1 and not re.search(r'///|;|\|',next(iter(s)))}
result=[];gene_rows=[];probe_rows=[];sample_rows=[];sens=[];universes=[]
def calculate(dataset,probes,mat,samples,contrasts,unit,mapping=None):
    mapping=map_valid if mapping is None else mapping
    assert mat.shape==(len(probes),len(samples)) and np.isfinite(mat).all()
    grouped=defaultdict(list)
    for i,p in enumerate(probes):grouped[p].append(i)
    probe_values={p:np.median(mat[idx],axis=0) for p,idx in grouped.items()}
    gene_probes=defaultdict(list)
    for p in grouped:
        if p in mapping:gene_probes[mapping[p]].append(p)
    gene_values={g:np.median(np.asarray([probe_values[p] for p in ids]),axis=0) for g,ids in gene_probes.items()}
    universes.append({'dataset':dataset,'native_rows':len(probes),'unique_probe_ids':len(grouped),'exact_annotated_probes':sum(p in mapping for p in grouped),'unambiguous_feature_labels':len(gene_probes),'samples':len(samples),'target_probe_ids':gene_probes.get('Pmp22',[]),'panel_probe_ids':{g:gene_probes.get(g,[]) for g in wanted},'scale':'source-normalized intensity, no additional log; log base not verified','detection':'native detection flags unavailable in normalized matrices; primary CPM floor not applicable','unit':unit})
    for name,ctrl,trt in contrasts:
        ia=[samples.index(s) for s in ctrl];ib=[samples.index(s) for s in trt]
        missing=[g for g in ['Pmp22',*panels['myelin7']] if g not in gene_values]
        r={'dataset':dataset,'contrast':name,'control':ctrl,'treated':trt,'n_control':len(ia),'n_treated':len(ib),'unit':unit,'missing_primary_genes':missing,'scale':'source-normalized-intensity difference, NOT asserted log2 fold change','detection_eligible':None,'status':'exploratory array; unknown detection/scale qualification'}
        if 'Pmp22' in gene_values:r['Pmp22']=stats(gene_values['Pmp22'][ia],gene_values['Pmp22'][ib])
        for panel,gs in panels.items():
            keep=[g for g in gs if g in gene_values]
            if keep:
                v=np.asarray([gene_values[g] for g in keep]).mean(axis=0);r[panel]=stats(v[ia],v[ib])|{'coverage':len(keep)}
        if not missing:
            v=gene_values['Pmp22']-np.asarray([gene_values[g] for g in panels['myelin7']]).mean(axis=0)
            r['selectivity']=stats(v[ia],v[ib]);r['target_vs_each_myelin']={g:float((gene_values['Pmp22']-gene_values[g])[ib].mean()-(gene_values['Pmp22']-gene_values[g])[ia].mean()) for g in panels['myelin7']}
            for drop in panels['myelin7']:
                v1=gene_values['Pmp22']-np.asarray([gene_values[g] for g in panels['myelin7'] if g!=drop]).mean(axis=0)
                sens.append({'dataset':dataset,'contrast':name,'kind':'leave_one_marker','omitted':drop,'effect':float(v1[ib].mean()-v1[ia].mean())})
            for omit in ia+ib:
                aa=[i for i in ia if i!=omit];bb=[i for i in ib if i!=omit]
                sens.append({'dataset':dataset,'contrast':name,'kind':'leave_one_sample','omitted':samples[omit],'effect':float(v[bb].mean()-v[aa].mean())})
        else:r['selectivity']=None
        for g in wanted:
            if g not in gene_values:continue
            v=gene_values[g];gene_rows.append({'dataset':dataset,'contrast':name,'gene':g,'probes':';'.join(gene_probes[g]),'control_mean':float(v[ia].mean()),'treated_mean':float(v[ib].mean()),**stats(v[ia],v[ib])})
            for p in gene_probes[g]:probe_rows.append({'dataset':dataset,'contrast':name,'gene':g,'probe':p,'spots':len(grouped[p]),**stats(probe_values[p][ia],probe_values[p][ib])})
            for i in ia+ib:sample_rows.append({'dataset':dataset,'contrast':name,'sample':samples[i],'arm':'control' if i in ia else 'treated','gene':g,'normalized_value':float(v[i])})
        result.append(r)

with gzip.open(source('GSE163132_series_matrix.txt.gz'),'rt') as f:
    meta={}
    for line in f:
        if line.startswith('!Sample_title') or line.startswith('!Sample_geo_accession'):
            row=next(csv.reader([line],delimiter='\t'));meta[row[0]]=row[1:]
        if line.startswith('!series_matrix_table_begin'):break
    reader=csv.reader(f,delimiter='\t');head=next(reader);rows=[]
    for row in reader:
        if row[0].startswith('!'):break
        rows.append(row)
samples=head[1:];assert samples==meta['!Sample_geo_accession'];titles=dict(zip(samples,meta['!Sample_title']))
contrasts=[]
for day in [1,3,7,14,21]:
    a=[s for s in samples if titles[s].startswith('0d_')];b=[s for s in samples if titles[s].startswith(f'{day}d_')];assert len(a)==len(b)==3
    contrasts.append((f'co_culture_d{day}_vs_d0',a,b))
calculate('GSE163132',[r[0] for r in rows],np.array([[float(v) for v in r[1:]] for r in rows]),samples,contrasts,'three independent donor experiments per time in series; no verified cross-time pairing; morphologically selected LMD SCs, d0 not co-cultured')
with source('E-MEXP-3491.matrix.txt').open() as f:
    reader=csv.reader(f,delimiter='\t');head=next(reader);kind=next(reader);rows=list(reader)
    assert kind[0]=='Name' and set(kind[1:])=={'Normalized'}
samples=head[1:]
with source('E-MEXP-3491.sdrf.txt').open() as f:
    sdrf=list(csv.DictReader(f,delimiter='\t'))
assert set(samples)=={r['Hybridization Name'] for r in sdrf}
contrasts=[]
for cell in ['schwann cells','dorsal root ganglia and schwann cells']:
    a=[r['Hybridization Name'] for r in sdrf if r['Factor Value[CELL_TYPE]']==cell and r['Factor Value[COMPOUND]']=='none']
    b=[r['Hybridization Name'] for r in sdrf if r['Factor Value[CELL_TYPE]']==cell and r['Factor Value[COMPOUND]']=='calcitriol']
    assert len(a)==len(b)==2
    assert all(r['Factor Value[DOSE]']=='500' for r in sdrf if r['Hybridization Name'] in b)
    contrasts.append((f'calcitriol_24h_{cell}',a,b))
# The processed Name column is mixed GeneName/EST identifiers, not ProbeName.
# Use one native export for annotation-only, verifying every row name/order;
# never use its numerical signal columns or re-normalize raw array measurements.
native=[]
with source('Schwanncellscontrol1-annotation-only.txt').open() as f:
    for line in f:
        if line.startswith('FEATURES'):
            columns=line.rstrip('\n').split('\t');break
    for raw in csv.reader(f,delimiter='\t'):
        if raw and raw[0]=='DATA':
            d=dict(zip(columns,raw));native.append({k:d[k] for k in ['ProbeName','GeneName','ControlType']})
assert len(native)==len(rows)
mismatches=[{'row_zero_based':i,'processed_name':r[0],'native_name':d['GeneName'],'probe':d['ProbeName']} for i,(r,d) in enumerate(zip(rows,native)) if r[0]!=d['GeneName']]
# Preserve and EXCLUDE the observed non-panel name corruptions (e.g. sept-10).
# Do not repair source names, assign the bad rows to genes, or relax panel mapping.
assert len(mismatches)==18 and all(d['processed_name'] not in wanted and d['native_name'] not in wanted for d in mismatches)
bad_probes={d['probe'] for d in mismatches}
(O/'array-annotation-mismatches.json').write_text(json.dumps(mismatches,indent=2))
native_map=defaultdict(set)
for d in native:
    if d['ControlType']=='0' and d['GeneName'] and d['ProbeName'] not in bad_probes:native_map[d['ProbeName']].add(d['GeneName'])
native_map={p:next(iter(gs)) for p,gs in native_map.items() if len(gs)==1}
calculate('E-MEXP-3491',[d['ProbeName'] for d in native],np.array([[float(v) for v in r[1:]] for r in rows]),samples,contrasts,'two pooled-culture preparations per arm; donor/pool overlap unknown; SDRF/paper 500nM conflicts IDF10nM; native GeneName/ProbeName annotation: all rows correspond except18 retained/excluded nonpanel-name corruptions',mapping=native_map)
for filename,rows in [('array-gene-effects.tsv',gene_rows),('array-probe-effects.tsv',probe_rows),('array-sample-values.tsv',sample_rows),('array-sensitivities.tsv',sens)]:
    with (O/filename).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
summary={'inputs':inputs,'array_spec_sha256':hashlib.sha256((Q/'inputs/array-spec.json').read_bytes()).hexdigest(),'panel_spec_sha256':hashlib.sha256((Q/'inputs/panel-spec.json').read_bytes()).hexdigest(),'universes':universes,'contrasts':result}
(O/'array-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
for r in result:print(r['dataset'],r['contrast'],'missing',r['missing_primary_genes'],'target',r.get('Pmp22'),'myelin',r.get('myelin7'),'selectivity',r['selectivity'])
for u in universes:print('UNIVERSE',u)
