"""Exploratory perturbation selectivity from full native measured backgrounds.
No cross-study normalization, causal fraction fit or source code execution.
"""
import csv,gzip,hashlib,itertools,json,os
from pathlib import Path
import numpy as np
from scipy.stats import t
WS=Path(os.environ['BIO_WORKSPACE']); Q=WS/'questions/q_6a3a0a07fa5d4da1'; OUT=Q/'outputs'
SPEC=json.loads((Q/'inputs/panel-spec.json').read_text()); PANELS=SPEC['panels']
INPUTS={}; summaries=[]; gene_rows=[]; sample_rows=[]; sensitivities=[]; universes=[]
def blob(h):
    p=WS/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    INPUTS[h]=str(p);return p
def load_two(p):
    with gzip.open(p,'rt') as f: rows=[r.strip().split('\t') for r in f if r.strip()]
    assert all(len(r)==2 for r in rows)
    symbols=[r[0] for r in rows]; values=np.array([float(r[1]) for r in rows])
    specials={s:float(v) for s,v in zip(symbols,values) if s.startswith('__')}
    keep=[i for i,s in enumerate(symbols) if not s.startswith('__')]
    return [symbols[i] for i in keep],values[keep],specials

def ci(a,b):
    a=np.asarray(a);b=np.asarray(b);eff=float(b.mean()-a.mean())
    va=a.var(ddof=1)/len(a);vb=b.var(ddof=1)/len(b);se=float(np.sqrt(va+vb))
    if se==0:return {'effect':eff,'ci_low':eff,'ci_high':eff,'df':None}
    df=float((va+vb)**2/(va*va/(len(a)-1)+vb*vb/(len(b)-1)))
    width=float(t.ppf(.975,df)*se)
    return {'effect':eff,'ci_low':eff-width,'ci_high':eff+width,'df':df}

def analyze(dataset,genes,counts,samples,contrasts,metadata,semantics):
    assert len(genes)==len(set(genes)), 'duplicate native gene symbols require an explicit mapping decision'
    assert counts.shape==(len(genes),len(samples)) and np.isfinite(counts).all() and (counts>=0).all()
    lib=counts.sum(axis=0);assert (lib>0).all();cpm=counts/lib*1e6
    positive=(counts>0).all(axis=1);assert positive.sum()>100
    geo=np.exp(np.log(counts[positive]).mean(axis=1))
    sf=np.median(counts[positive]/geo[:,None],axis=0)
    # Scale normalized counts to CPM-like units for the pseudocount sensitivity only.
    mr=(counts/sf)/np.median(lib/sf)*1e6
    index={g:i for i,g in enumerate(genes)}
    universes.append({'dataset':dataset,'features':len(genes),'samples':len(samples),'all_zero_features':int((counts==0).all(axis=1).sum()),'normalization_positive_genes':int(positive.sum()),'library_sums':dict(zip(samples,map(float,lib))),'semantics':semantics,'noninteger_values':int((counts!=np.floor(counts)).sum()),'panels_present':{k:[g for g in v if g in index] for k,v in PANELS.items()},'target_present':'Pmp22' in index})
    for s in samples:
        assert s in metadata
    for contrast in contrasts:
        name,control,treated,unit=contrast
        ia=[samples.index(s) for s in control];ib=[samples.index(s) for s in treated]
        measured=[g for g in ['Pmp22',*sum(PANELS.values(),[])] if g in index]
        measured=list(dict.fromkeys(measured))
        base={g:float(cpm[index[g],ia].mean()) for g in measured}
        absent=[g for g in ['Pmp22',*PANELS['myelin7']] if g not in index]
        floor=[g for g in ['Pmp22',*PANELS['myelin7']] if g in base and base[g]<1]
        selected=[g for g in PANELS['myelin7'] if g in base and base[g]>=1]
        eligible=not absent and not floor
        tag='myelin7' if eligible else 'exploratory_detected_myelin'
        r={'dataset':dataset,'contrast':name,'control':control,'treated':treated,'unit':unit,'n_control':len(ia),'n_treated':len(ib),'primary_eligible':eligible,'missing':absent,'baseline_floor_failures':floor,'control_mean_cpm':base,'exploratory_panel':selected if not eligible else None,'uncertainty':'Welch 95% conditional on independent library pools/culture preparations; no animal-level CI; exploratory and small-n, no multiplicity claim'}
        logs=np.log2(cpm+.1)
        if 'Pmp22' in index:r['Pmp22']=ci(logs[index['Pmp22'],ia],logs[index['Pmp22'],ib])
        for panel,gs in PANELS.items():
            present=[index[g] for g in gs if g in index]
            if present:r[panel]=ci(logs[present][:,ia].mean(axis=0),logs[present][:,ib].mean(axis=0))|{'coverage':len(present)}
        if not eligible:r['primary_selectivity']=None
        if len(selected)>=4 and 'Pmp22' in base and base['Pmp22']>=1:
            idx=[index[g] for g in selected];v=logs[index['Pmp22']]-logs[idx].mean(axis=0)
            r[tag+'_selectivity']=ci(v[ia],v[ib]);r['selectivity_endpoint']=tag
            if eligible:r['primary_selectivity']=r[tag+'_selectivity']
            # Complete enumeration is descriptive conditional on exchangeable units; never confirms n=2 contrasts.
            obs=abs(v[ib].mean()-v[ia].mean()); vv=v[ia+ib];stats=[]
            for a in itertools.combinations(range(len(vv)),len(ia)):
                b=[i for i in range(len(vv)) if i not in a];stats.append(abs(vv[b].mean()-vv[list(a)].mean()))
            r['conditional_exact_permutation_p']=float(np.mean(np.asarray(stats)>=obs-1e-12))
            for norm,mat in [('CPM',cpm),('median_ratio',mr)]:
                for pseudocount in [0,.1,1]:
                    needed=mat[[index['Pmp22'],*idx]][:,ia+ib]
                    if pseudocount==0 and (needed<=0).any(): continue
                    z=np.log2(needed+pseudocount);diff=z[0]-z[1:].mean(axis=0)
                    effect=float(diff[len(ia):].mean()-diff[:len(ia)].mean())
                    sensitivities.append({'dataset':dataset,'contrast':name,'endpoint':tag,'kind':'normalization_pseudocount','normalization':norm,'pseudocount':pseudocount,'omitted':None,'effect':effect})
            for drop in selected:
                remain=[index[g] for g in selected if g!=drop];d=logs[index['Pmp22']]-logs[remain].mean(axis=0)
                sensitivities.append({'dataset':dataset,'contrast':name,'endpoint':tag,'kind':'leave_one_marker','normalization':'CPM','pseudocount':.1,'omitted':drop,'effect':float(d[ib].mean()-d[ia].mean())})
            for omit in ia+ib:
                aa=[i for i in ia if i!=omit];bb=[i for i in ib if i!=omit]
                sensitivities.append({'dataset':dataset,'contrast':name,'endpoint':tag,'kind':'leave_one_library','normalization':'CPM','pseudocount':.1,'omitted':samples[omit],'effect':float(v[bb].mean()-v[aa].mean())})
            r['target_vs_each_myelin']={g:float((logs[index['Pmp22'],ib]-logs[index[g],ib]).mean()-(logs[index['Pmp22'],ia]-logs[index[g],ia]).mean()) for g in selected}
        summaries.append(r)
        for gene in measured:
            effects=ci(logs[index[gene],ia],logs[index[gene],ib])
            gene_rows.append({'dataset':dataset,'contrast':name,'gene':gene,'control_mean_cpm':base[gene],'treated_mean_cpm':float(cpm[index[gene],ib].mean()),**effects})
        for j in ia+ib:
            for gene in measured:sample_rows.append({'dataset':dataset,'contrast':name,'sample':samples[j],'arm':'control' if j in ia else 'treated','gene':gene,'native_count':float(counts[index[gene],j]),'cpm':float(cpm[index[gene],j]),'metadata':json.dumps(metadata[samples[j]],sort_keys=True)})

h='7f8b8f20b3fd13166075450994acd62bf4bcbc610818f79e917a50856a4247fb'
with gzip.open(blob(h),'rt') as f:
    samples=next(f).strip().split('\t');rows=[line.rstrip('\n').split('\t') for line in f if line.strip()]
genes=[r[0] for r in rows];counts=np.array([[float(x) for x in r[1:]] for r in rows])
fields=json.loads((OUT/'fields-GSE177037-full.json').read_text());meta={}
for acc,f in fields.items():
    if acc.startswith('GSM'):
        key=f['Sample_description'][0];meta[key]={'accession':acc,'title':f['Sample_title'][0],'characteristics':f['Sample_characteristics_ch1'],'donor_ids':None}
contrasts=[]
for compartment in ['Schwann Cell','Whole Nerve']:
    a=[s for s in samples if meta[s]['title'].startswith(compartment+' Uncrushed')]
    for day in [3,5,7]:
        b=[s for s in samples if meta[s]['title'].startswith(f'{compartment} {day}d')]
        assert len(a)==len(b)==2
        contrasts.append((f'{compartment}_d{day}_vs_naive',a,b,'two pooled libraries per arm; >=10 nerves/pool; cross-pool donor overlap unresolved'))
analyze('GSE177037',genes,counts,samples,contrasts,meta,'native RSEM expected counts; full provided symbol-level universe; fraction values retained')

samples=[];vectors=[];genes=None;meta={};specials={}
fields=json.loads((OUT/'fields-GSE104324.json').read_text())
assets=json.loads((OUT/'list-GSE104324.json').read_text())['items']
for arm,term in [('control','mock'),('treated','treated')]:
    for i in [1,2,3]:
        receipt=json.loads((OUT/f'fetch-NRG1-{arm}{i}.json').read_text());assert receipt['outcome']=='available_full'
        gs,val,sp=load_two(blob(receipt['blob']))
        if genes is None:genes=gs
        assert genes==gs,'native universes differ'
        matches=[a for a in assets if a['asset_revision']==receipt['previous_revision']];assert len(matches)==1
        acc=matches[0]['name'].split('_')[0];f=fields[acc];title=f['Sample_title'][0]
        assert title.startswith(f'{term} {i} ('), (acc,title,arm,i)
        assert '10 nM recombinant soluble NRG1' in f['Sample_treatment_protocol_ch1'][0]
        samples.append(acc);vectors.append(val);specials[acc]=sp
        meta[acc]={'title':title,'characteristics':f['Sample_characteristics_ch1'],'donor_ids':None,'source_unit':'three biological replicates stated in primary paper; exact split/pairing not established'}
analyze('GSE104324',genes,np.array(vectors).T,samples,[('soluble_NRG1_10nM_6h',samples[:3],samples[3:],'three independent experiments stated in GEO; donor/pair map unresolved; unpaired analysis')],meta,'native htseq-count gene counts; excluded __ special counters from gene library size only; complete measured genes retained')
(OUT/'NRG1-special-counters.json').write_text(json.dumps(specials,indent=2))
for fname,rows in [('screen-gene-effects.tsv',gene_rows),('screen-sample-values.tsv',sample_rows),('screen-sensitivities.tsv',sensitivities)]:
    with (OUT/fname).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
result={'question':'q_6a3a0a07fa5d4da1','stage':'exploratory discovery, before independent validation','panel_spec_sha256':hashlib.sha256((Q/'inputs/panel-spec.json').read_bytes()).hexdigest(),'inputs':INPUTS,'universes':universes,'contrasts':summaries}
(OUT/'screen-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False))
for r in summaries:print(r['dataset'],r['contrast'],'eligible',r['primary_eligible'],'floor',r['baseline_floor_failures'],'Pmp22',r['Pmp22'],'myelin7',r['myelin7'],'selectivity',r.get('primary_selectivity'),r.get('exploratory_detected_myelin_selectivity'))
print('UNIVERSES',[(u['dataset'],u['features'],u['samples']) for u in universes])
