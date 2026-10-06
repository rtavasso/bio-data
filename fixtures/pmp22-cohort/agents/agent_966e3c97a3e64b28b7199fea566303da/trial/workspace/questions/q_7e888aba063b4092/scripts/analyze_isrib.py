"""Independent-context test using constituent native counts and source gene mapping."""
import hashlib
import json
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from scipy import stats

R=Path(__file__).resolve().parents[1]
S=R/'inputs'/'sources'
OUT=R/'outputs'
plan=json.loads((R/'inputs'/'analysis-plan-r001.json').read_text())
assert (R/'inputs'/'independent-context-prediction-r001.json').exists()
wb=openpyxl.load_workbook(S/'elife05033s001.xlsx',read_only=True,data_only=False)
ws=wb['expression table tm isrib no ps']
rows=list(ws.iter_rows(values_only=True))
headers=['feature']+list(rows[1][1:])
source=pd.DataFrame(rows[2:],columns=headers).dropna(subset=['feature']).set_index('feature')
assert source.index.is_unique
# GEO sample titles define exact assay, condition and replicate; no inferred donors.
metadata=[]
current=None
for num,line in enumerate((S/'GSE65778.soft').read_text().splitlines(),1):
    if line.startswith('^SAMPLE = '):
        current={'GSM':line.split(' = ')[1],'source_line':num}
        metadata.append(current)
    if current is not None and line.startswith('!Sample_title = '):
        current['title']=line.split(' = ',1)[1]
    if current is not None and line.startswith('!Sample_characteristics_ch1 = '):
        current.setdefault('characteristics',[]).append(line.split(' = ',1)[1])
pd.DataFrame(metadata).to_csv(OUT/'GSE65778-sample-map.tsv',sep='\t',index=False)
frames={}
inputs={}
for m in metadata:
    name=m['GSM']
    f=pd.read_csv(S/name,sep='\t',compression='gzip',header=None,names=['feature','CDS_size','count'],na_values=['N/A']).set_index('feature')
    assert f.index.is_unique
    assert f['count'].notna().all() and (f['count']>=0).all()
    assert (f['count']==np.floor(f['count'])).all()
    frames[m['title']]=f
    inputs[name]=hashlib.sha256((S/name).read_bytes()).hexdigest()
raw=pd.DataFrame({k:f['count'] for k,f in frames.items()})
lengths=pd.DataFrame({k:f['CDS_size'] for k,f in frames.items()})
raw.to_csv(OUT/'GSE65778-full-native-counts.tsv.gz',sep='\t',compression='gzip')
lengths.to_csv(OUT/'GSE65778-full-native-lengths.tsv.gz',sep='\t',compression='gzip')
assert source.index.isin(raw.index).all()
# Audit every source-paper constituent cell, not only target or significant rows.
source_checks=[]
constituents=pd.DataFrame(index=source.index)
for title in raw:
    sourcecol=title if title.startswith('ribo_') else title.removeprefix('mrna_')+'_hek'
    a=pd.to_numeric(source[sourcecol],errors='raise')
    b=raw.loc[source.index,title]
    mismatch=~np.isclose(a,b,equal_nan=True)
    source_checks.append({'sample':title,'source_column':sourcecol,'compared_rows':len(source),'mismatches':int(mismatch.sum())})
    constituents[title]=a
# Failed exact-export equivalence is retained, not repaired by stripping versions.
# Analyse the paper's OWN 16-column constituent table as one self-contained matrix.
# The separate GEO exports remain preserved and are not used to supply target RNA.
assert constituents.notna().all().all()
assert (constituents>=0).all().all()
assert (constituents==np.floor(constituents)).all().all()
constituents.to_csv(OUT/'GSE65778-paper-constituent-counts.tsv.gz',sep='\t',compression='gzip')
# Source all-expression table is distinct from source selected-significant tables.
meta=source[['gene','size']].copy().rename_axis('native_feature')
meta['feature']=meta.index
meta['control_RNA_mean']=constituents.loc[meta.index,['mrna_untr_a','mrna_untr_b']].mean(axis=1)
meta['gene']=meta['gene'].fillna('UNMAPPED_'+meta['feature'])
selected=meta.sort_values(['gene','control_RNA_mean','feature'],ascending=[True,False,True]).drop_duplicates('gene')
selected.to_csv(OUT/'GSE65778-feature-map.tsv',sep='\t',index=False)
x=constituents.loc[selected.index].copy()
x.index=selected.gene
assert x.notna().all().all()
assert x.index.is_unique
assert 'PMP22' in x.index
# Keep the gene-background and a broader native-feature-intersection normalization separate.
conditions=['untr','isrib','tm','tmisrib']
contrasts=[('untr','tm'),('untr','tmisrib'),('untr','isrib'),('tm','tmisrib')]
allres=[]
allvalues=[]
summary={'input_sha256':inputs,'native_rows_per_library':{k:len(f) for k,f in frames.items()},'native_union_rows':len(raw),'native_complete_intersection_rows':int(raw.notna().all(axis=1).sum()),'source_paper_rows':len(source),'source_comparisons':source_checks,'representative_genes':len(x),'source_target_rows':source.loc[source.gene=='PMP22'].reset_index().to_dict('records'),'PMP22_counts':x.loc['PMP22'].to_dict(),'PMP22_size_by_library':lengths.loc[selected.loc[selected.gene=='PMP22'].index[0]].to_dict(),'source_duplicates_by_gene':int(meta.gene.duplicated().sum()),'tests':{},'normalization_factors':{},'global_scale_warning':'all normalizations are relative, no external per-cell RPF calibration','RNA_selection':'GEO says IlluminaTruSeqstranded prep, article references Ingolia protocol; exact polyA versus depletion selection not resolved by inspected source. Do not infer RNA-end equivalence.'}

def contrast_matrix(y,cond0,cond1):
    a=y[[cond0+'_a',cond0+'_b']].to_numpy()
    b=y[[cond1+'_a',cond1+'_b']].to_numpy()
    v0=a.var(axis=1,ddof=1)/2
    v1=b.var(axis=1,ddof=1)/2
    v=v0+v1
    with np.errstate(divide='ignore',invalid='ignore'):
        df=v*v/(v0*v0+v1*v1)
        se=np.sqrt(v)
        eff=b.mean(axis=1)-a.mean(axis=1)
        t=eff/se
        p=2*stats.t.sf(abs(t),df)
        hw=stats.t.ppf(.975,df)*se
    return pd.DataFrame({'effect':eff,'ci_low':eff-hw,'ci_high':eff+hw,'p_nominal':p,'df':df},index=y.index)

summary['analysis_representation']='Paper source data 1 all-expression constituent counts; exact GEO export equivalence FAILED. No cross-version target RNA joining.'
summary['source_target_size']=source.loc[source.gene=='PMP22','size'].tolist()
for norm in ['sum','median_ratio','source_all_feature_sum']:
    sf=pd.Series(index=x.columns,dtype=float)
    for assay in ['mrna','ribo']:
        cols=[c for c in x if c.startswith(assay+'_')]
        z=x[cols]
        if norm=='sum':
            fac=z.sum()
        elif norm=='source_all_feature_sum':
            fac=constituents[cols].sum()
        else:
            pos=z.loc[(z>0).all(axis=1)]
            gm=np.exp(np.log(pos).mean(axis=1))
            fac=pos.div(gm,axis=0).median()
        sf.loc[cols]=fac/np.exp(np.log(fac).mean())
    summary['normalization_factors'][norm]=sf.to_dict()
    for pc in [0.0,.5,1.0]:
        with np.errstate(divide='ignore',invalid='ignore'):
            logs=np.log2(x+pc).sub(np.log2(sf),axis=1)
            y=pd.DataFrame({c+'_'+rep:logs['ribo_'+c+'_'+rep]-logs['mrna_'+c+'_'+rep] for c in conditions for rep in ['a','b']})
        for c0,c1 in contrasts:
            key=c1+'_minus_'+c0
            r=contrast_matrix(y,c0,c1)
            cols=[a+'_'+c+'_'+rep for a in ['ribo','mrna'] for c in [c0,c1] for rep in ['a','b']]
            eligible=(x[cols]>=10).all(axis=1)
            target=r.loc['PMP22'].to_dict()
            target['eligible']=bool(eligible['PMP22'])
            target['replicate_number_contrasts']=[float(y.loc['PMP22',c1+'_'+rep]-y.loc['PMP22',c0+'_'+rep]) for rep in ['a','b']]
            target['sample_log_association']=y.loc['PMP22'].to_dict()
            for assay in ['mrna','ribo']:
                target[assay+'_log2FC']=float(logs.loc['PMP22',[assay+'_'+c1+'_'+rep for rep in ['a','b']]].mean()-logs.loc['PMP22',[assay+'_'+c0+'_'+rep for rep in ['a','b']]].mean())
            target['eligible_background']=int(eligible.sum())
            target['target_background_percentile']=float(100*(r.loc[eligible,'effect']<r.loc['PMP22','effect']).mean())
            if pc==.5:
                panel=[g for g in plan['membrane_panel'] if g!='PMP22' and g in x.index and eligible[g]]
                resid=y.sub(y.loc[panel].median(),axis=1)
                target['membrane_panel']=panel
                target['target_minus_membrane']=contrast_matrix(resid,c0,c1).loc['PMP22'].to_dict()
                r['gene']=r.index
                r['contrast']=key
                r['normalization']=norm
                r['eligible_all_counts_ge10']=eligible
                allres.append(r)
            summary['tests'][norm+'_pc'+str(pc)+'_'+key]=target
        if pc==.5:
            out=y.copy()
            out.insert(0,'gene',out.index)
            out.insert(1,'normalization',norm)
            allvalues.append(out)
        # Four-condition difference of assay differences: interaction of ISRIB with Tm.
        w={'untr':1,'isrib':-1,'tm':-1,'tmisrib':1}
        means={c:y.loc['PMP22',[c+'_a',c+'_b']].mean() for c in conditions}
        variances={c:y.loc['PMP22',[c+'_a',c+'_b']].var(ddof=1)/2 for c in conditions}
        effect=sum(w[c]*means[c] for c in conditions)
        v=sum(variances.values())
        df=v*v/sum(a*a for a in variances.values())
        hw=stats.t.ppf(.975,df)*np.sqrt(v)
        summary['tests'][norm+'_pc'+str(pc)+'_factorial_interaction']={'effect':effect,'ci_low':effect-hw,'ci_high':effect+hw,'df':df,'p_nominal':float(2*stats.t.sf(abs(effect/np.sqrt(v)),df))}
results=pd.concat(allres,ignore_index=True)
results.to_csv(OUT/'GSE65778-full-background-effects.tsv.gz',sep='\t',index=False,compression='gzip')
results.loc[results.gene.isin(plan['membrane_panel']+plan['stress_panel'])].to_csv(OUT/'GSE65778-controls.tsv',sep='\t',index=False)
pd.concat(allvalues).to_csv(OUT/'GSE65778-sample-log-association.tsv.gz',sep='\t',index=False,compression='gzip')
# Preserve any nonfinite statistic as null, not zero.
def clean(x):
    if isinstance(x,dict):
        return {k:clean(v) for k,v in x.items()}
    if isinstance(x,list):
        return [clean(v) for v in x]
    if isinstance(x,(float,np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x,np.integer):
        return int(x)
    return x
summary=clean(summary)
(OUT/'GSE65778-effects.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['normalization_factors','tests']},indent=2))
print(json.dumps({k:v for k,v in summary['tests'].items() if k.startswith('sum_pc0.5')},indent=2))
