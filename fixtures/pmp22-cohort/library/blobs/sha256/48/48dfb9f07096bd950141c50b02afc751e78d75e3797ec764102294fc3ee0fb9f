from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';W=Q.parents[1]
H={'MEF':'14ca149475bf0716e53a54775c0519d6f111deb5a41e17db368a4633de9a0169','NIH':'6f893c348e2297eb7bac4961c0cb6ab0dd3fcd512eb90124f7715a9fc77287'}
# Literal verified fetch hash.
H['NIH']='6f893c348e2297eb7bac49bf61c0cb6ab0dd3fcd512eb90124f7715a9fc77287'
def read(h):
 p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;return pd.read_csv(p,compression='gzip',sep='\t',index_col=0)
a,b=[read(h) for h in H.values()];assert a.index.is_unique and b.index.is_unique
f=pd.read_csv(O/'shared-gene-effects.tsv',sep='\t',index_col=0);assert set(a.index)==set(b.index)==set(f.index)
assert (a>=0).all().all() and (b>=0).all().all() and np.isfinite(a).all().all() and np.isfinite(b).all().all()
cs=['PERK_WT_Control','PERK_WT_Tg2hr'];ns=['NIH3T3_Cont','NIH3T3_Tg2hr'];c=a[cs].join(b[ns]);refs=f.index[(f.MEF_control>=10)&(f.NIH_control>=10)&f.unfloored_2h&(f.baseline_max_abs_log2distance<=1)].difference(['Pmp22']);assert len(refs)==1276
res=[];effects=[];normalizers={}
for mode in ['CPM','median_ratio']:
 if mode=='CPM':sf=c.sum(axis=0)/1e6
 else:
  g=c[(c>0).all(axis=1)];sf=g.div(np.exp(np.log(g).mean(axis=1)),axis=0).median(axis=0)
 normalizers[mode]=sf.to_dict();n=c.div(sf,axis=1);me=np.log2(n[cs[1]].where(n[cs[1]]>0)/n[cs[0]].where(n[cs[0]]>0));ni=np.log2(n[ns[1]].where(n[ns[1]]>0)/n[ns[0]].where(n[ns[0]]>0));de=me-ni
 out=pd.DataFrame({'MEF_log2FC':me,'NIH_log2FC':ni,'delta':de,'mode':mode,'fixed_TPM_baseline_match':c.index.isin(refs),'all_expected_counts_ge20':(c>=20).all(axis=1)});effects.append(out)
 for floor in [0,20]:
  ids=refs[(c.loc[refs]>floor).all(axis=1)] if floor==0 else refs[(c.loc[refs]>=floor).all(axis=1)]
  x=de.loc[ids];pdlt=float(de['Pmp22']);tpm=f.loc[ids,'delta_2h'];diff=(x-x.median())-(tpm-tpm.median())
  res.append(dict(normalization=mode,count_floor=floor,n=len(ids),excluded_fixed_reference_genes=refs.difference(ids).tolist(),Pmp22_min_expected_count=float(c.loc['Pmp22'].min()),Pmp22_MEF=float(me['Pmp22']),Pmp22_NIH=float(ni['Pmp22']),Pmp22_delta=pdlt,reference_median=float(x.median()),Pmp22_relative_residual=float(pdlt-x.median()),Pmp22_percentile=float((x<pdlt).mean()),count_vs_TPM_residual_difference=float(pdlt-x.median()-(f.loc['Pmp22','delta_2h']-tpm.median())),reference_abs_countTPM_residual_difference_median=float(diff.abs().median())))
pd.concat(effects).to_csv(O/'counts-all-effects.tsv',sep='\t',index_label='gene');c.to_csv(O/'counts-primary-source.tsv',sep='\t',index_label='gene');pd.DataFrame(res).drop(columns='excluded_fixed_reference_genes').to_csv(O/'counts-reference-summary.tsv',sep='\t',index=False)
s=dict(inputs=H,units='RSEMfractionalexpectedcounts; per-library compositional normalization, not absolute synthesis',normalizers=normalizers,pmp22_expected_counts=c.loc['Pmp22'].to_dict(),results=res,limits='Same13unreplicatedlibraries; retrospective. FixedTPMbaseline references; count floor sensitivity is not independentvalidation. Gene-specific effective length effect can be assessed but underlyingmapping artifact remains possible.')
(O/'counts-summary.json').write_text(json.dumps(s,indent=2,allow_nan=False)+'\n');print(json.dumps(s,indent=2,allow_nan=False))
