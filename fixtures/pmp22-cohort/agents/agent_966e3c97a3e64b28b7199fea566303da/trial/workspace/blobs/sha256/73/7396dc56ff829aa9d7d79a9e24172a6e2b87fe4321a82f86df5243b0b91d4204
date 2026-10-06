from pathlib import Path
import json,hashlib,io,zipfile
import pandas as pd,numpy as np,openpyxl
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/iteration';W=Q.parents[1];inv=json.loads((O/'followup-input-objects.json').read_text())
def source(n):
 h=inv[n]['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;return p
# Source representation audit of all Gonen TableS5A gene measurements.
z=zipfile.ZipFile(source('Gonen-supplements.zip'));w=openpyxl.load_workbook(io.BytesIO(z.read('41598_2019_38705_MOESM5_ESM.xlsx')),data_only=False,read_only=True)
tables={}
for s in w:
 rows=list(s.values);assert not any(isinstance(v,str) and v.startswith('=') for row in rows for v in row)
 d=pd.DataFrame(rows[2:],columns=rows[1]).set_index('Gene_Id');tables[s.title]=d
 d.loc[['Pmp22']].to_csv(O/f'gonens5-{s.title}-pmp22.tsv',sep='\t')
a=pd.read_csv(source('GSE118660_MEF-tpm.txt.gz'),compression='gzip',sep='\t',index_col=0)
common=a.columns.intersection(tables['A'].columns);shared=a.index.intersection(tables['A'].index);eq=np.isclose(a.loc[shared,common].to_numpy(float),tables['A'].loc[shared,common].to_numpy(float)).all();unmatched=[str(x) for x in a.index.difference(shared)]
b=pd.read_csv(source('GSE118660_3t3-TPM.txt.gz'),compression='gzip',sep='\t',index_col=0)
print('NIH3T3 deposited columns',b.columns.tolist());print(b.loc['Pmp22'].to_dict())
# TE source table. Keep exact source units and conditional linear-ratio interpretation separate.
te=pd.read_csv(source('GSE103667_TE.norm.txt.gz'),compression='gzip',sep='\t');cols=['TE.DMSO1','TE.THAP1','TE.DMSO2','TE.THAP2'];te['eligible_positive_all4']=np.isfinite(te[cols]).all(axis=1)&(te[cols]>0).all(axis=1)
for rep in [1,2]:
 te[f'difference_rep{rep}']=te[f'TE.THAP{rep}']-te[f'TE.DMSO{rep}'];te[f'log2_ratio_if_linear_rep{rep}']=np.log2(te[f'TE.THAP{rep}'].where(te[f'TE.THAP{rep}']>0)/te[f'TE.DMSO{rep}'].where(te[f'TE.DMSO{rep}']>0))
te['mean_log2_ratio_if_linear']=te[['log2_ratio_if_linear_rep1','log2_ratio_if_linear_rep2']].mean(axis=1);te.to_csv(O/'TE-all-source-effects.tsv',sep='\t',index=False);te[te.name=='Pmp22'].to_csv(O/'TE-pmp22-source-effects.tsv',sep='\t',index=False)
# One gene summary, not independent RefSeq rows; median of row effects, no summation of duplicated counts.
tg=te[te.eligible_positive_all4].groupby('name').mean(numeric_only=True);tg['mean_log2_ratio_if_linear']=te[te.eligible_positive_all4].groupby('name').mean_log2_ratio_if_linear.median();tg['percentile']=tg.mean_log2_ratio_if_linear.rank(pct=True);tg.to_csv(O/'TE-gene-summary.tsv',sep='\t')
# Granule assay, source has no recoverable spike calibrators by named labels.
frames=[];audit=[];annotation_mismatch=set()
for rep in range(1,4):
 f=pd.read_csv(source(f'GSE90869_rep{rep}.txt.gz'),compression='gzip',sep='\t');
 if rep==1:
  feature_map=f[['#geneID','geneName']].copy();feature_map.to_csv(O/'granule-source-feature-map.tsv',sep='\t',index_label='source_row_zero_based')
 else:
  assert f['#geneID'].equals(feature_map['#geneID'])
  annotation_mismatch.update(f.index[f.geneName!=feature_map.geneName].tolist())
 f=f.drop(columns='#geneID')
 cc=f.drop(columns='geneName');assert np.isfinite(cc).all().all() and (cc>=0).all().all()
 audit.append({'rep':rep,'source_rows':len(f),'exact_spike_label_hits':f[f.geneName.str.lower().isin(['dact5c','dgapdh1','drps7'])].index.tolist()})
 frames.append(f if rep==1 else f.drop(columns='geneName'))
f=frames[0].join(frames[1:]);f[f.geneName=='Pmp22'].to_csv(O/'granule-pmp22-source-counts.tsv',sep='\t')
# Keep all rows; choose one representative transcript per gene by max mean cytoplasmic control abundance, then lexical ID.
f=f.drop(index=list(annotation_mismatch));ctrl=[c for c in f if c.startswith('Cyt_DMSO')];choose=f[ctrl].mean(axis=1).rename('control_mean');meta=pd.DataFrame({'id':f.index,'gene':f.geneName,'control_mean':choose}).sort_values(['gene','control_mean','id'],ascending=[True,False,True]);ids=meta.drop_duplicates('gene').id;g=f.loc[ids].copy();g.index=g.geneName;g=g.drop(columns='geneName');results=[]
for stress,control,nrep in [('THAP','DMSO',3),('AS','CO',2),('HS','CO',2)]:
 cs=[f'{frac}_{cond}_Rep{i}' for frac in ['Cyt','Ins'] for cond in [stress,control] for i in range(1,nrep+1)];elig=(g[cs]>=50).all(axis=1)
 diffs=[];norm_diffs=[];sf=(g.loc[elig,cs].div(np.exp(np.log(g.loc[elig,cs]).mean(axis=1)),axis=0)).median(axis=0)
 for rep in range(1,nrep+1):
  ratio=np.log2(g[f'Ins_{stress}_Rep{rep}'].where(g[f'Ins_{stress}_Rep{rep}']>0)/g[f'Cyt_{stress}_Rep{rep}'].where(g[f'Cyt_{stress}_Rep{rep}']>0))-np.log2(g[f'Ins_{control}_Rep{rep}'].where(g[f'Ins_{control}_Rep{rep}']>0)/g[f'Cyt_{control}_Rep{rep}'].where(g[f'Cyt_{control}_Rep{rep}']>0))
  # Per-replicate centering eliminates uniform unknown fraction multiplier; endpoint is relative to eligible median gene.
  centered=ratio-ratio[elig].median();shift=np.log2(sf[f'Ins_{stress}_Rep{rep}']/sf[f'Cyt_{stress}_Rep{rep}'])-np.log2(sf[f'Ins_{control}_Rep{rep}']/sf[f'Cyt_{control}_Rep{rep}']);mr=ratio-shift
  diffs.append(centered);norm_diffs.append(mr)
  results.append(pd.DataFrame({'gene':g.index,'stress':stress,'replicate':rep,'eligible':elig.to_numpy(),'uncalibrated_log2_fraction_change':ratio.to_numpy(),'median_centered_change':centered.to_numpy(),'median_ratio_change':mr.to_numpy(),'rank_percentile':ratio.where(elig).rank(pct=True).to_numpy()}))
r=pd.concat(results).replace([np.inf,-np.inf],np.nan);r.to_csv(O/'granule-all-relative-effects.tsv',sep='\t',index=False)
panel=['Pmp22','Xiap','Ago3','Creb1','Rictor','Brca1','Actb','Gapdh','G3bp1'];r[r.gene.isin(panel)].to_csv(O/'granule-panel-relative-effects.tsv',sep='\t',index=False)
rg=r[(r.stress=='THAP')&r.eligible].groupby('gene').median_centered_change.mean();joined=pd.concat([tg.mean_log2_ratio_if_linear.rename('TE_log2ratio_conditional'),rg.rename('relative_granule_change')],axis=1).dropna();joined.to_csv(O/'TE-granule-gene-comparison.tsv',sep='\t');rho=joined.corr(method='spearman').iloc[0,1]
summary={'gonens5A_matches_GEO_shared_cells':bool(eq),'gonens5A_shared_genes':len(shared),'gonens5A_unmatched_GEO_labels':unmatched,'gonens5A_label_limit':'25 date-like gene strings in GEO do not match Excel native date cells; no gene identity guessed. Pmp22 matches exactly.','Gonen_Pmp22_late_cluster':int(tables['A'].loc['Pmp22','Late_cluster']),'Gonen_NIH3T3_source_values':b.loc['Pmp22'].to_dict(),'Gonen_NIH3T3_limit':'TableS5B labels late column8h; GEO/paper methods say7h. Same numbers inspected; retain discrepancy, no fabricated timing. MEF1uM and NIH3T3 200nM differ in dose as well as cell line.','TE_source_rows':len(te),'TE_positive_eligible_rows':int(te.eligible_positive_all4.sum()),'TE_eligible_genes':len(tg),'TE_Pmp22_rows':int((te.name=='Pmp22').sum()),'TE_Pmp22_gene_percentile':float(tg.loc['Pmp22','percentile']),'TE_Pmp22_log2ratio_if_linear':float(tg.loc['Pmp22','mean_log2_ratio_if_linear']),'TE_unit_caveat':'GEO TE.norm source values nonnegative up to1032; likely linear TE while paper plots log10 TE. Explicit file units absent; log2 ratios conditional on linear interpretation, direct source-unit decrease holds regardless. Raw coverage processing not performed.','granule_source_audit':audit,'granule_total_unique_genes':len(g),'granule_duplicate_RefSeq_labels':int(feature_map['#geneID'].duplicated().sum()),'excluded_annotation_mismatch_rows':sorted(annotation_mismatch),'granule_Pmp22_min_source_count':float(f[f.geneName=='Pmp22'].drop(columns='geneName').min().min()),'granule_Pmp22_results':r[r.gene=='Pmp22'].to_dict(orient='records'),'TE_RG_joint_genes':len(joined),'TE_RG_spearman_descriptive':float(rho),'granule_limits':'No named spike calibrator rows in deposits. Absolute %RG or absolute stress-induced recruitment unidentifiable; relative rankings and centered changes only. Cyt includes insoluble fraction. 3 ER biological replicates source-documented, 2 other-stress reps. Not independent of TE source study; altered stress affects granule recovery. No granule-causality claim.'}
(O/'followup-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2))
