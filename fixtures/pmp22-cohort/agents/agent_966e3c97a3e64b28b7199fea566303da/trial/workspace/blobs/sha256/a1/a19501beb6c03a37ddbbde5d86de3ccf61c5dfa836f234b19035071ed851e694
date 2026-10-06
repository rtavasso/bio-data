"""Retrospective shared-time footprint analysis; no population p-values."""
from pathlib import Path
import hashlib,json,platform
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';W=Q.parents[1]
HASHES={'MEF':'7740f1a5d816fd8a98a17e67e6c6621ca438c5afd14addb62309f9148f3c6dc7','NIH':'8b837d3c0a48e869522484f68d0837994ee9c932e2dac52ef6dd5f679b6928d7'}
def read(h):
 p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h
 return pd.read_csv(p,sep='\t',compression='gzip',index_col=0)
a,b=[read(h) for h in HASHES.values()]
assert a.index.is_unique and b.index.is_unique
shared=a.index.intersection(b.index).sort_values();a=a.loc[shared];b=b.loc[shared]
assert np.isfinite(a).all().all() and np.isfinite(b).all().all() and (a>=0).all().all() and (b>=0).all().all()
f=pd.DataFrame({'MEF_control':a.PERK_WT_Control,'NIH_control':b.NIH3T3_Cont})
for time,ac,bc in [('2h','PERK_WT_Tg2hr','NIH3T3_Tg2hr'),('late8vs7h','PERK_WT_Tg8hr','NIH3T3_Tg7hr')]:
 f['MEF_'+time]=a[ac];f['NIH_'+time]=b[bc]
 for context,control in [('MEF','MEF_control'),('NIH','NIH_control')]:
  f[context+'_log2FC_'+time]=np.log2(f[context+'_'+time].where(f[context+'_'+time]>0)/f[control].where(f[control]>0))
 f['delta_'+time]=f['MEF_log2FC_'+time]-f['NIH_log2FC_'+time]
 f['unfloored_'+time]=(f[['MEF_control','NIH_control','MEF_'+time,'NIH_'+time]]>4).all(axis=1)
 f['positive_'+time]=(f[['MEF_control','NIH_control','MEF_'+time,'NIH_'+time]]>0).all(axis=1)
base=np.log2(f[['MEF_control','NIH_control']].where(f[['MEF_control','NIH_control']]>0));diff=base-base.loc['Pmp22'];f['baseline_distance']=np.sqrt((diff**2).sum(axis=1,skipna=False));f['baseline_max_abs_log2distance']=diff.abs().max(axis=1,skipna=False)
rows=[];members=[]
for time in ['2h','late8vs7h']:
 for threshold in [4,10,20]:
  for eligibility in ['unfloored','positive']:
   eligible=f[(f[['MEF_control','NIH_control']]>=threshold).all(axis=1)&f[eligibility+'_'+time]].drop(index='Pmp22',errors='ignore')
   for method in ['all','box0.5','box1','box1.5','box2','nearest100','nearest250','nearest500']:
    g=eligible
    if method.startswith('box'):g=g[g.baseline_max_abs_log2distance<=float(method[3:])]
    if method.startswith('nearest'):g=g.sort_values(['baseline_distance'],kind='stable').head(int(method[7:]))
    if len(g)==0:continue
    x=g['delta_'+time];p=float(f.loc['Pmp22','delta_'+time]);me=g['MEF_log2FC_'+time];ni=g['NIH_log2FC_'+time]
    r=dict(time=time,baseline_min=threshold,eligibility=eligibility,reference=method,n=len(g),pmp22_eligible=bool((f.loc['Pmp22',['MEF_control','NIH_control']]>=threshold).all() and f.loc['Pmp22',eligibility+'_'+time]),pmp22_delta=p,reference_median_delta=float(x.median()),pmp22_minus_reference_median=float(p-x.median()),pmp22_percentile=float(((x<p).sum()+.5*(x==p).sum())/len(x)),reference_q025=float(x.quantile(.025)),reference_q25=float(x.quantile(.25)),reference_q75=float(x.quantile(.75)),reference_q975=float(x.quantile(.975)),MEF_median=float(me.median()),NIH_median=float(ni.median()),opposed_MEFup_NIHdown_fraction=float(((me>0)&(ni<0)).mean()),strong_opposed_fraction=float(((me>=1)&(ni<=-1)).mean()),abs_delta_ge_pmp22_fraction=float((x.abs()>=abs(p)).mean()),MEF_NIH_spearman=float(me.corr(ni,method='spearman')),max_baseline_distance=float(g.baseline_max_abs_log2distance.max()))
    rows.append(r)
    if threshold==10 and eligibility=='unfloored':
     h=g.copy();h['time']=time;h['reference']=method;members.append(h)
res=pd.DataFrame(rows);res.to_csv(O/'reference-sensitivity.tsv',sep='\t',index=False)
f.to_csv(O/'shared-gene-effects.tsv',sep='\t',index_label='gene');pd.concat(members).to_csv(O/'reference-members.tsv',sep='\t',index_label='gene')
primary=res[(res.time=='2h')&(res.baseline_min==10)&(res.eligibility=='unfloored')&(res.reference=='box1')].iloc[0].to_dict()
summary={'inputs':HASHES,'shared_gene_labels':len(shared),'MEF_only':len(a.index.difference(b.index)),'source_value_min':{'MEF':float(a.min().min()),'NIH':float(b.min().min())},'pmp22':f.loc['Pmp22'].to_dict(),'primary':primary,'primary_reference_rules':'Baseline>=10TPM both contexts; all contrast cells>4; +/-1log2 control TPM each context, exclude Pmp22. Empirical gene distributions, not biological confidence intervals.','exposure':'Retrospective: source matrices and Pmp22 responses exposed in inherited work.','limits':'n1/library per condition; no matched total RNA, no absolute synthesis calibration; MEF1uM versus NIH3T3 200nM. Late8vs7h is time-mismatched secondary. No causal attribution or gene bootstrap inference.','environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}}
(O/'summary-r001.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
g=f[(f[['MEF_control','NIH_control']]>=10).all(axis=1)&f.unfloored_2h].drop(index='Pmp22');m=g[g.baseline_max_abs_log2distance<=1]
fig,ax=plt.subplots(1,3,figsize=(14,4.4));ax[0].scatter(g.NIH_log2FC_2h,g.MEF_log2FC_2h,s=4,alpha=.15,c='gray',label=f'Eligible genes ({len(g)})');ax[0].scatter(m.NIH_log2FC_2h,m.MEF_log2FC_2h,s=10,alpha=.6,c='#347da2',label=f'Baseline matched ({len(m)})');ax[0].scatter(f.loc['Pmp22','NIH_log2FC_2h'],f.loc['Pmp22','MEF_log2FC_2h'],s=80,c='#c54b36',marker='*',label='Pmp22');ax[0].axhline(0,c='k',lw=.5);ax[0].axvline(0,c='k',lw=.5);ax[0].set(xlabel='NIH3T3 2h log2 footprint fold change',ylabel='MEF WT 2h log2 footprint fold change',title='Same assay and time; dose/cell model differ');ax[0].legend(fontsize=7)
ax[1].hist(m.delta_2h,bins=25,color='#347da2');ax[1].axvline(f.loc['Pmp22','delta_2h'],c='#c54b36',label='Pmp22');ax[1].set(xlabel='MEF minus NIH3T3 log2 fold change',ylabel='Reference genes',title='Two-context baseline matching');ax[1].legend()
s=res[(res.time=='2h')&(res.baseline_min==10)&(res.eligibility=='unfloored')];ax[2].scatter(s.pmp22_percentile*100,np.arange(len(s)),color='#347da2');ax[2].set_yticks(np.arange(len(s)),s.reference);ax[2].set(xlim=(0,100),xlabel='Pmp22 descriptive percentile',title='Reference-set sensitivity')
fig.suptitle('Pmp22 footprint context comparison — retrospective, unreplicated',fontsize=12);fig.tight_layout();fig.savefig(O/'context-comparison.png',dpi=180);plt.close(fig)
print(json.dumps({'pmp22':summary['pmp22'],'primary':primary},indent=2,allow_nan=False))
