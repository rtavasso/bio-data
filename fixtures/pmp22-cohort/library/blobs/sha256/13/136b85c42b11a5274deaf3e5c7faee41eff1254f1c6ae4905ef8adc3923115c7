"""Independent E3/chromatin follow-ups under the previously fixed program.
Nedd4 uses the native gene table; transcript-level Kallisto files are NOT relabeled as genes.
RNF40 uses six native HTSeq files; three pools per arm, not nine independent mice.
"""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import openpyxl
import pandas as pd
from scipy import stats

Q=Path(__file__).resolve().parents[1]
WS=Q.parents[1]
plan=json.loads((Q/'inputs/analysis-plan.r001.json').read_text())
panel=plan['primary_program']['genes']
targets=plan['targets']
controls=plan['controls']
genes=list(dict.fromkeys(targets+panel+sum(controls.values(),[])))
inputs={}


def blob(h):
    p=WS/'blobs/sha256'/h[:2]/h
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    inputs[h]=str(p)
    return p


def estimate(values,c,t):
    a,b=values.loc[c].to_numpy(float),values.loc[t].to_numpy(float)
    effect=float(b.mean()-a.mean())
    va,vb=a.var(ddof=1)/len(a),b.var(ddof=1)/len(b)
    se=float(np.sqrt(va+vb))
    df=float((va+vb)**2/(va**2/(len(a)-1)+vb**2/(len(b)-1))) if se else None
    h=float(stats.t.ppf(.975,df)*se) if se else 0.0
    ci=[effect-h,effect+h]
    loo=[float(b.mean()-np.delete(a,i).mean()) for i in range(len(a))]
    loo += [float(np.delete(b,i).mean()-a.mean()) for i in range(len(b))]
    return {'effect':effect,'ci95':ci,'se':se,'df':df,'loo_sample_effect_range':[min(loo),max(loo)],
            'preserved_0.25':bool(ci[0]>=-.25 and ci[1]<=.25),'preserved_0.5':bool(ci[0]>=-.5 and ci[1]<=.5),
            'nondepleted_0.5':bool(ci[0]>-.5),'minimum_symmetric_bound':max(abs(v) for v in ci)}


def read_workbook(h):
    with blob(h).open('rb') as f:
        wb=openpyxl.load_workbook(f,read_only=True,data_only=False)
        assert len(wb.sheetnames)==1
        sheet=wb[wb.sheetnames[0]]
        rows=sheet.iter_rows(values_only=True)
        header=next(rows)
        return pd.DataFrame(rows,columns=header)


nd_native=read_workbook('13a3d8dd3037b8f3d81219c6c7e84d121d5fe915cd88a4ca1d411eaa0257fe8d')
blank=nd_native.isna().all(axis=1)
assert int(blank.sum())==12131
excluded_rows=(np.flatnonzero(blank)+2).tolist()
assert excluded_rows==list(range(13617,25748))
nd=nd_native.loc[~blank].set_index('Identifier')
assert nd.index.is_unique
cols=[s for s in nd.columns if s.endswith('[normalized count]')]
c=[s for s in cols if s.startswith('Control')]
t=[s for s in cols if s.startswith('MpzNedd4cKO')]
assert len(c)==len(t)==4
count=nd[cols].astype(float)
fpkmcols=[s for s in nd.columns if s.endswith('[FPKM]')]
fpkm=nd[fpkmcols].astype(float)
# Positional mapping is explicit in the preserved source header, with the same group/replicate numbers.
for normcol,fpkmcol in zip(cols,fpkmcols,strict=True):
    assert normcol.split(' [')[0].strip()==fpkmcol.split(' [')[0].strip()
fpkm.columns=cols
sets=[{'id':'Nedd4_cKO_P5','study':'GSE217272 / PMC11662984 TableS1','counts':count,'symbols':nd['gene_name'],
       'control':c,'treatment':t,'primary':'source_normalized','variants':{'source_normalized':(count,.5),'FPKM':(fpkm,.1)},
       'units':'native author-normalized gene counts; source FPKM sensitivity, not raw counts',
       'source_header':list(nd.columns),'source_effect':nd['log2 Ratio'],
       'excluded_nonmeasurement_rows':{'reason':'fully empty trailing formatted Excel rows, not measured zeros','count':len(excluded_rows),'source_row_range':[min(excluded_rows),max(excluded_rows)],'original_sheet_data_row_count':len(nd_native)},
       'unit_limit':'4 source mice per genotype, endoneurium-enriched P5 nerve; litter/donor mapping unavailable; no cross-protein pairing',
       'feature_universe_limit':'Full exported TableS1, not a verified genome-wide/unfiltered measurement universe; no library-sum renormalization of this table',
       'not_used':'Kallisto transcript-level counts inspected but not aggregated without their original tx2gene annotation'}]

receipts=json.loads((Q/'outputs/rnf40-fetches.json').read_text())
cols={}
meta=json.loads((Q/'outputs/rnf40-geo-metadata.json').read_text())['profiles'][0]['facts']['related_source_context']
meta={r['body']['fields']['Sample_geo_accession'][0]:r['body']['fields'] for r in meta if 'Sample_geo_accession' in r.get('body',{}).get('fields',{})}
for r in receipts:
    if not r['name'].endswith('.txt.gz'):
        continue
    sample=r['name'].split('_')[0]
    with gzip.open(blob(r['receipt']['blob']),'rt') as f:
        d=pd.read_csv(f,sep='\t',header=None,names=['symbol','count'],index_col='symbol')
    assert d.index.is_unique
    cols[sample]=d['count']
x=pd.DataFrame(cols).sort_index(axis=1)
assert x.shape[1]==6 and not x.isna().any().any()
removed=[i for i in x.index if i.startswith('__')]
x=x.drop(removed)
assert (x>=0).all().all() and np.equal(x,np.floor(x)).all().all()
c=[s for s in x if 'Rnf40_ctrl' in meta[s]['Sample_title'][0]]
t=[s for s in x if 'Rnf40_cko' in meta[s]['Sample_title'][0]]
assert len(c)==len(t)==3
pos=(x>0).all(axis=1)
g=np.exp(np.log(x.loc[pos]).mean(axis=1))
sf=x.loc[pos].div(g,axis=0).median(axis=0)
normalized=x.div(sf,axis=1)
workbook=next(r for r in receipts if r['name'].endswith('.xlsx'))
source=read_workbook(workbook['receipt']['blob']).set_index(None)
assert source.index.is_unique
checks={}
for col,group in [('ctrl_baseMean',c),('cko_baseMean',t)]:
    source_vals=pd.to_numeric(source[col],errors='coerce')
    shared=x.index.intersection(source_vals.index)
    valid=shared[source_vals.loc[shared].notna() & (source_vals.loc[shared]>10)]
    checks[col]={'gene_count':len(valid),'pearson':float(np.corrcoef(normalized.loc[valid,group].mean(axis=1),source_vals.loc[valid])[0,1])}
    assert checks[col]['pearson']>.999
sets.append({'id':'Rnf40_cKO_P14','study':'GSE146629 / PMC7498331','counts':x,'symbols':pd.Series(x.index,index=x.index),
             'control':c,'treatment':t,'primary':'median_ratio','variants':{'median_ratio':(normalized,.5),'CPM':(x.div(x.sum(),axis=1)*1e6,.1)},
             'units':'native integer HTSeq gene counts','size_factors':sf.to_dict(),'positive_genes':int(pos.sum()),
             'native_DESeq2_mean_checks':checks,'removed_counters':removed,'source_effect':pd.to_numeric(source['log2FoldChange'],errors='coerce'),
             'unit_limit':'3 source RNA pools per arm, each reported as 3 sciatic nerves; no 9-mouse or matched RNA/ChIP claim; intervals conditional on pool independence',
             'metadata_conflicts':'GEO says alignment mm10/Bowtie2 but Genome_build mm9; paper mm9/TOPHAT. Library prep descriptions also differ. No coordinate analysis or assembly repair performed; native gene labels used.'})

results=[]
values=[]
effects=[]
for ds in sets:
    x,symbols,c,t=ds['counts'],ds['symbols'],ds['control'],ds['treatment']
    assert np.isfinite(x).all().all() and (x>=0).all().all()
    ids={}
    coverage={}
    for gene in genes:
        hits=symbols.index[symbols==gene].tolist()
        item={'matches':len(hits),'feature_ids':hits,'eligible':False}
        if len(hits)==1:
            i=hits[0]
            ids[gene]=i
            item.update({'control_min_native':float(x.loc[i,c].min()),'eligible':bool(x.loc[i,c].min()>=10),
                         'quality_flags':'not exported in selected source','control_values':x.loc[i,c].tolist(),'treated_values':x.loc[i,t].tolist()})
        coverage[gene]=item
    eligible=all(coverage[g]['eligible'] for g in panel+targets)
    r={k:v for k,v in ds.items() if k not in ['counts','symbols','variants','source_effect']}
    r.update({'native_rows':len(x),'coverage':coverage,'primary_eligible':eligible,'variants':{}})
    for variant,(m,pc) in ds['variants'].items():
        logs=np.log2(m+pc)
        selected=pd.DataFrame({g:logs.loc[i,c+t] for g,i in ids.items()})
        metrics={g:selected[g] for g in targets if g in selected}
        if set(panel)<=set(selected):
            metrics['myelin7']=selected[panel].mean(axis=1)
            for g in ['Egr2','Sox10']:
                metrics['myelin7-minus-'+g]=metrics['myelin7']-selected[g]
                metrics['Pmp22-minus-'+g]=selected['Pmp22']-selected[g]
        for name,p in controls.items():
            if set(p)<=set(selected):
                metrics[name]=selected[p].mean(axis=1)
        stats_={k:estimate(v,c,t) for k,v in metrics.items()}
        for key in ['myelin7','myelin7-minus-Egr2','myelin7-minus-Sox10']:
            loo=[]
            for omit in panel:
                v=selected[[g for g in panel if g!=omit]].mean(axis=1)
                if '-minus-' in key:
                    v=v-selected[key.split('-minus-')[1]]
                loo.append(estimate(v,c,t)['effect'])
            stats_[key]['loo_gene_effect_range']=[min(loo),max(loo)]
        r['variants'][variant]=stats_
        for sample in c+t:
            for gene,i in ids.items():
                values.append({'contrast':ds['id'],'variant':variant,'sample':sample,'group':'control' if sample in c else 'perturbed','gene':gene,'feature':i,'expression':float(m.loc[i,sample]),'log2_expression':float(logs.loc[i,sample]),'pseudocount':pc})
        if variant==ds['primary']:
            eff=logs[t].mean(axis=1)-logs[c].mean(axis=1)
            for i,v in eff.items():
                effects.append({'contrast':ds['id'],'feature':i,'symbol':symbols.loc[i],'log2_change':v})
            r['selected_source_reported_effects']={g:float(ds['source_effect'].loc[i]) for g,i in ids.items() if i in ds['source_effect'].index and pd.notna(ds['source_effect'].loc[i])}
    rr=r['variants'][ds['primary']]
    r['frozen_shared_pattern_pass']=bool(eligible and rr['Egr2']['nondepleted_0.5'] and rr['Sox10']['nondepleted_0.5'] and rr['myelin7-minus-Egr2']['ci95'][1]<-.5)
    results.append(r)
    print(ds['id'],'primary_eligible',eligible,'shared_pattern_pass',r['frozen_shared_pattern_pass'])
    for name in ['Egr2','Sox10','Pmp22','myelin7','myelin7-minus-Egr2','myelin7-minus-Sox10']:
        print(name,rr[name])
(Q/'outputs/followup-contrasts.json').write_text(json.dumps({'input_blobs':inputs,'plan_sha256':hashlib.sha256((Q/'inputs/followup-plan.r001.json').read_bytes()).hexdigest(),'contrasts':results},indent=2,allow_nan=False)+'\n')
pd.DataFrame(values).to_csv(Q/'outputs/followup-sample-expression.tsv',sep='\t',index=False)
pd.DataFrame(effects).to_csv(Q/'outputs/followup-all-gene-effects.tsv',sep='\t',index=False)
