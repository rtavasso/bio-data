"""Independent effect arithmetic, count-matched ranks and falsification controls."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
a=json.loads((OUT/'GSE55195-effects.json').read_text())
b=json.loads((OUT/'GSE65778-effects.json').read_text())
checks=[]
for source,result in [('GSE55195',a),('GSE65778',b)]:
    for key,entry in result['tests'].items():
        if source=='GSE55195':
            diff=entry['RPF_log2FC']-entry['RNA_log2FC']
        elif 'factorial' not in key:
            diff=entry['ribo_log2FC']-entry['mrna_log2FC']
        else:
            continue
        assert np.isclose(diff,entry['effect'],atol=1e-12)
        checks.append({'source':source,'test':key,'RPF_minus_RNA_matches_interaction':True})
# Verify point estimate and small-n uncertainty directly from native target counts.
sf=b['normalization_factors']['sum']
counts=b['PMP22_counts']
ratio={c+'_'+r:np.log2((counts['ribo_'+c+'_'+r]+.5)/(counts['mrna_'+c+'_'+r]+.5))-np.log2(sf['ribo_'+c+'_'+r]/sf['mrna_'+c+'_'+r]) for c in ['untr','tm','isrib','tmisrib'] for r in ['a','b']}
u=np.array([ratio['untr_a'],ratio['untr_b']])
v=np.array([ratio['tm_a'],ratio['tm_b']])
test=stats.ttest_ind(v,u,equal_var=False)
interval=test.confidence_interval()
ref=b['tests']['sum_pc0.5_tm_minus_untr']
assert np.isclose(v.mean()-u.mean(),ref['effect'])
assert np.allclose([interval.low,interval.high],[ref['ci_low'],ref['ci_high']])
# Background matching uses baseline RNA AND baseline RPF, never outcome rank.
raw=pd.read_csv(OUT/'GSE65778-paper-constituent-counts.tsv.gz',sep='\t',index_col=0)
rep=pd.read_csv(OUT/'GSE65778-feature-map.tsv',sep='\t')
x=raw.loc[rep.feature].copy()
x.index=rep.gene
base_rna=x[['mrna_untr_a','mrna_untr_b']].mean(axis=1)
base_rpf=x[['ribo_untr_a','ribo_untr_b']].mean(axis=1)
mask=base_rna.between(base_rna['PMP22']/2,base_rna['PMP22']*2)&base_rpf.between(base_rpf['PMP22']/2,base_rpf['PMP22']*2)&(x.index!='PMP22')
effects=pd.read_csv(OUT/'GSE65778-full-background-effects.tsv.gz',sep='\t')
matched=[]
for (norm,contrast),g in effects.groupby(['normalization','contrast']):
    g=g.set_index('gene')
    eligible=g.eligible_all_counts_ge10.reindex(x.index)
    target=g.loc['PMP22','effect']
    bg=g.loc[mask&eligible,'effect']
    matched.append({'normalization':norm,'contrast':contrast,'background_genes':len(bg),'median_effect':float(bg.median()),'target_effect':float(target),'target_percentile':float(100*(bg<target).mean())})
(OUT/'GSE65778-countmatched-background.tsv').write_text(effects.loc[effects.gene.isin(x.index[mask])].to_csv(sep='\t',index=False))
# RNA CDS/total composition is a diagnostic, not a direct RNA-end measurement.
ct=a['target_CDS_counts']
tot=a['target_total_counts']
fractions={c:ct[c]/tot[c] for c in ct if c.startswith('RNA_')}
fraction_change=np.mean([np.log2(fractions['RNA_arsenite_'+r]) for r in ['1','2']])-np.mean([np.log2(fractions['RNA_control_'+r]) for r in ['1','2']])
report={'arithmetic_checks':checks,'independent_scipy_welch_check':{'effect':float(v.mean()-u.mean()),'ci_low':float(interval.low),'ci_high':float(interval.high),'p_nominal':float(test.pvalue)},'arsenite':{k:v for k,v in a['tests'].items() if 'pc0.5' in k},'arsenite_membrane':a['membrane_results'],'arsenite_countmatched':a['background'],'arsenite_RNA_CDS_to_total_fractions':fractions,'arsenite_log2_CDS_fraction_change':float(fraction_change),'tunicamycin':{k:v for k,v in b['tests'].items() if 'pc0.5' in k},'tunicamycin_countmatched':matched,'interpretation_boundary':'Ranks are descriptive, not significance; normalizers do not measure absolute flux. RNA-region sensitivity motivates processing/selection tests but does not establish APA or transcription initiation.'}
(OUT/'cross-context-validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print('All',len(checks),'assay-difference arithmetic checks and scipy Welch check passed.')
for k,v in report['arsenite'].items():
    print('ARS',k,'RNA',v['RNA_log2FC'],'RPF',v['RPF_log2FC'],'interaction',v['effect'],'CI',v['ci95'])
print('RNA CDS fraction',fractions,'log2 shift',fraction_change)
for k,v in report['tunicamycin'].items():
    print('TM',k,'effect',v['effect'],'CI',v.get('ci_low'),v.get('ci_high'))
print('COUNT MATCHED',json.dumps(matched))
controls=pd.read_csv(OUT/'GSE65778-controls.tsv',sep='\t')
print('STRESS CONTROLS',controls.loc[(controls.normalization=='sum')&controls.gene.isin(['ATF4','ATF5','DDIT3','PPP1R15A','IFRD1','SLC35A4','EMP1','EMP2','EMP3','ACTB','GAPDH']),['gene','contrast','effect','eligible_all_counts_ge10']].to_json(orient='records'))
