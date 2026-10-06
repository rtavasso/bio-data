"""Executed matched-assay discovery; counts are never reconstructed from TE."""
import hashlib
import itertools
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

ROOT=Path(__file__).resolve().parents[1]
S=ROOT/'inputs'/'sources'
OUT=ROOT/'outputs'
PLAN=json.loads((ROOT/'inputs'/'analysis-plan-r001.json').read_text())
files={
 'RPF_control_1':'GSM1331342','RNA_control_1':'GSM1331343',
 'RPF_arsenite_1':'GSM1331344','RNA_arsenite_1':'GSM1331345',
 'RPF_control_2':'GSM1331346','RNA_control_2':'GSM1331347',
 'RPF_arsenite_2':'GSM1331348','RNA_arsenite_2':'GSM1331349',
}

def welch(a,b):
    """Condition b minus a, biological sample variance, not read-level precision."""
    a=np.asarray(a,dtype=float)
    b=np.asarray(b,dtype=float)
    v0=np.var(a,ddof=1)/len(a)
    v1=np.var(b,ddof=1)/len(b)
    se=np.sqrt(v0+v1)
    effect=np.mean(b)-np.mean(a)
    if se==0:
        return {'effect':float(effect),'ci95':None,'p':None,'df':None,'se':0.0}
    df=(v0+v1)**2/(v0*v0/(len(a)-1)+v1*v1/(len(b)-1))
    half=stats.t.ppf(.975,df)*se
    return {'effect':float(effect),'ci95':[float(effect-half),float(effect+half)],'p':float(2*stats.t.sf(abs(effect/se),df)),'df':float(df),'se':float(se)}

frames={}
for label,name in files.items():
    f=pd.read_csv(S/name,sep='\t',compression='gzip',dtype={'RefSeq accession identifier':str})
    assert f['RefSeq accession identifier'].is_unique
    frames[label]=f.set_index('RefSeq accession identifier')
first=next(iter(frames.values()))
assert all(f.index.equals(first.index) for f in frames.values())
assert all(f['Gene'].equals(first['Gene']) for f in frames.values())
meta=first[['Gene','annotation type']].copy()
counts=pd.DataFrame({k:f['raw mapped reads, CDS'] for k,f in frames.items()})
total=pd.DataFrame({k:f['total raw mapped reads'] for k,f in frames.items()})
assert (counts.dropna().to_numpy()>=0).all()
meta['baseline_RNA_CDS']=counts[['RNA_control_1','RNA_control_2']].mean(axis=1)
meta['refseq']=meta.index
rep=(meta.loc[meta['annotation type']=='coding'].sort_values(['Gene','baseline_RNA_CDS','refseq'],ascending=[True,False,True]).drop_duplicates('Gene').copy())
selected=rep.index
x=counts.loc[selected].copy()
x.index=rep.Gene
xt=total.loc[selected].copy()
xt.index=rep.Gene
assert x.index.is_unique
assert x.notna().all().all()
assert (x==np.floor(x)).all().all()
raw=pd.concat([meta,counts.add_prefix('CDS_'),total.add_prefix('total_')],axis=1)
raw.to_csv(OUT/'GSE55195-full-native-feature-counts.tsv.gz',sep='\t',compression='gzip')
rep.to_csv(OUT/'GSE55195-representatives.tsv',sep='\t',index=False)
eligible=(x>=10).all(axis=1)
controls=['control_1','control_2']
treated=['arsenite_1','arsenite_2']
size_factors={}
all_results=[]
all_per_sample=[]
summary={'versions':{'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__},'inputs':{n:hashlib.sha256((S/n).read_bytes()).hexdigest() for n in files.values()},'native_features':len(meta),'representative_genes':len(rep),'eligible_genes':int(eligible.sum()),'representative_PMP22':rep.loc[rep.Gene=='PMP22','refseq'].tolist(),'target_CDS_counts':x.loc['PMP22'].to_dict(),'target_total_counts':xt.loc['PMP22'].to_dict(),'target_eligible':bool(eligible['PMP22']),'target_all_annotations':raw.loc[raw.Gene=='PMP22'].reset_index(drop=True).to_dict('records'),'tests':{},'membrane_results':{},'background':{},'limits':['n=2 independent biological preparations per condition','cross-condition pairing not proven; primary Welch uses no invented matching','polyA-selection may affect RNA recovery','count-sum and median-ratio normalizations identify relative occupancy only','CDS-sharing transcript vectors not biological replication','no transcript-position elongation or target protein completion measurement']}
for region in ['CDS','total']:
    data=x.copy()
    if region=='total':
        for col in data:
            if col.startswith('RNA_'):
                data[col]=xt[col]
    for norm in ['sum','median_ratio']:
        sf=pd.Series(index=data.columns,dtype=float)
        for assay in ['RPF','RNA']:
            cols=[c for c in data if c.startswith(assay+'_')]
            z=data[cols]
            if norm=='sum':
                factors=z.sum()
            else:
                pos=z.loc[(z>0).all(axis=1)]
                gm=np.exp(np.log(pos).mean(axis=1))
                factors=pos.div(gm,axis=0).median()
            factors=factors/np.exp(np.log(factors).mean())
            sf.loc[cols]=factors
        key=region+'_'+norm
        size_factors[key]=sf.to_dict()
        for pc in [0.0,.5,1.0]:
            with np.errstate(divide='ignore',invalid='ignore'):
                logs=np.log2(data+pc).sub(np.log2(sf),axis=1)
                y=pd.DataFrame({c:logs['RPF_'+c]-logs['RNA_'+c] for c in controls+treated})
            run=key+'_pc'+str(pc)
            target=y.loc['PMP22']
            assert np.isfinite(target).all()
            stat=welch(target[controls],target[treated])
            stat['replicate_number_contrasts']=[float(target[t]-target[c]) for c,t in zip(controls,treated,strict=True)]
            stat['all_between_condition_differences']=[float(target[t]-target[c]) for c,t in itertools.product(controls,treated)]
            for assay in ['RNA','RPF']:
                stat[assay+'_log2FC']=float(logs.loc['PMP22',[assay+'_'+c for c in treated]].mean()-logs.loc['PMP22',[assay+'_'+c for c in controls]].mean())
            stat['log2_association_per_sample']=target.to_dict()
            summary['tests'][run]=stat
            if pc==.5:
                for gene in x.index:
                    vals=y.loc[gene]
                    if not np.isfinite(vals).all():
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        result=welch(vals[controls],vals[treated])
                    all_results.append({'gene':gene,'analysis':key,'eligible_all_counts_ge10':bool(eligible[gene]),'effect':result['effect'],'ci_low':result['ci95'][0] if result['ci95'] else None,'ci_high':result['ci95'][1] if result['ci95'] else None,'p_nominal':result['p'],'df':result['df']})
                y.insert(0,'gene',y.index)
                y.insert(1,'analysis',key)
                all_per_sample.append(y)
                eff=y[treated].mean(axis=1)-y[controls].mean(axis=1)
                bg=eff.loc[eligible]
                target_baseline=x.loc['PMP22',['RNA_control_1','RNA_control_2']].mean()
                target_rpf=x.loc['PMP22',['RPF_control_1','RPF_control_2']].mean()
                mask=eligible & x[['RNA_control_1','RNA_control_2']].mean(axis=1).between(target_baseline/2,target_baseline*2) & x[['RPF_control_1','RPF_control_2']].mean(axis=1).between(target_rpf/2,target_rpf*2)
                bgmatch=eff.loc[mask & (eff.index!='PMP22')]
                summary['background'][key]={'eligible_median':float(bg.median()),'target_percentile':float(100*(bg<eff['PMP22']).mean()),'countmatched_n':len(bgmatch),'countmatched_median':float(bgmatch.median()),'target_countmatched_percentile':float(100*(bgmatch<eff['PMP22']).mean())}
                membrane=[g for g in PLAN['membrane_panel'] if g!='PMP22' and g in y.index and eligible[g]]
                panel=y.loc[membrane,controls+treated].median()
                residual=target-panel
                summary['membrane_results'][key]={'eligible_panel':membrane,'target_minus_panel':welch(residual[controls],residual[treated]),'panel_sample_medians':panel.to_dict()}
results=pd.DataFrame(all_results)
results.to_csv(OUT/'GSE55195-full-background-effects.tsv.gz',sep='\t',index=False,compression='gzip')
pd.concat(all_per_sample).to_csv(OUT/'GSE55195-sample-log-association.tsv.gz',sep='\t',index=False,compression='gzip')
panelset=set(PLAN['membrane_panel']+PLAN['stress_panel'])
results.loc[results.gene.isin(panelset)].to_csv(OUT/'GSE55195-controls.tsv',sep='\t',index=False)
summary['panel_coverage']={g:{'present':g in x.index,'eligible':bool(eligible[g]) if g in eligible else False,'CDS_counts':x.loc[g].to_dict() if g in x.index else None} for g in sorted(panelset)}
summary['size_factors']=size_factors
(OUT/'GSE55195-effects.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:summary[k] for k in ['native_features','representative_genes','eligible_genes','representative_PMP22','target_CDS_counts','target_total_counts','target_eligible','tests','membrane_results','background']},indent=2))
