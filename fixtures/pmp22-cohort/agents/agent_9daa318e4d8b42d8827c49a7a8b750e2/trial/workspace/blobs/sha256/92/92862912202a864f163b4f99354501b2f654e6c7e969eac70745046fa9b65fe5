from pathlib import Path
import hashlib,json,io,zipfile
import numpy as np,pandas as pd,openpyxl
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';W=Q.parents[1]
H={'MEF':'7740f1a5d816fd8a98a17e67e6c6621ca438c5afd14addb62309f9148f3c6dc7','NIH':'8b837d3c0a48e869522484f68d0837994ee9c932e2dac52ef6dd5f679b6928d7','supp':'37583638e8e9aec98b62feb7749e0d8446113914a2733dd8986051b549b6da01'}
def source(h):
 p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;return p
a=pd.read_csv(source(H['MEF']),compression='gzip',sep='\t',index_col=0);b=pd.read_csv(source(H['NIH']),compression='gzip',sep='\t',index_col=0)
z=zipfile.ZipFile(source(H['supp']));w=openpyxl.load_workbook(io.BytesIO(z.read('41598_2019_38705_MOESM5_ESM.xlsx')),data_only=False,read_only=True)
rs=list(w['A'].values);assert not any(isinstance(x,str) and x.startswith('=') for r in rs for x in r)
c=pd.DataFrame(rs[2:],columns=rs[1]).set_index('Gene_Id');cl=c[['Repression_cluster','Early_cluster','Late_cluster']];cl.to_csv(O/'source-cluster-memberships.tsv',sep='\t',index_label='source_gene_label')
f=a.join(b,how='inner');base=np.log2(f[['PERK_WT_Control','NIH3T3_Cont']].where(f[['PERK_WT_Control','NIH3T3_Cont']]>0));dist=(base-base.loc['Pmp22']).abs().max(axis=1,skipna=False)
def stats(g,me,ni,pme,pni):
 de=me-ni;p=pme-pni
 return dict(n=len(g),pmp22_MEF=float(pme),pmp22_comparator=float(pni),pmp22_delta=float(p),median_delta=float(de.median()),median_relative_Pmp22=float(p-de.median()),percentile=float(((de<p).sum()+.5*(de==p).sum())/len(de)),MEF_median=float(me.median()),comparator_median=float(ni.median()),opposite_fraction=float(((me>0)&(ni<0)).mean()))
rows=[]
for time,ac,bc in [('2h','PERK_WT_Tg2hr','NIH3T3_Tg2hr'),('late8vs7h','PERK_WT_Tg8hr','NIH3T3_Tg7hr')]:
 for mode in ['baseline_only_clip4','all_contrast_gt4','baseline_only_clip1']:
  mask=(f[['PERK_WT_Control','NIH3T3_Cont']]>=10).all(axis=1)
  if mode=='all_contrast_gt4':mask&=(f[[ac,bc]]>4).all(axis=1)
  t=f.clip(lower=1 if mode.endswith('clip1') else 4);me=np.log2(t[ac]/t.PERK_WT_Control);ni=np.log2(t[bc]/t.NIH3T3_Cont)
  for program in ['all','Late_cluster','Early_cluster','Repression_cluster']:
   keep=mask.copy()
   if program!='all':keep &= cl[program].reindex(f.index).eq(1)
   for match in ['all','box1']:
    k=keep.copy()
    if match=='box1':k &=dist<=1
    ids=f.index[k].difference(['Pmp22'])
    if not len(ids):continue
    r=stats(f.loc[ids],me.loc[ids],ni.loc[ids],me['Pmp22'],ni['Pmp22']);r.update(time=time,mode=mode,program=program,match=match);rows.append(r)
    if time=='2h' and mode=='baseline_only_clip4' and match=='box1' and program=='all':
     norm=[]
     for s1,s2 in [(1,1),(.1,10),(10,.1),(2,3)]:
      delta=(me.loc[ids]+np.log2(s1))-(ni.loc[ids]+np.log2(s2));pv=(me['Pmp22']+np.log2(s1))-(ni['Pmp22']+np.log2(s2));norm.append(dict(MEF_scale=s1,NIH_scale=s2,relative_residual=float(pv-delta.median()),percentile=float((delta<pv).mean())))
     (O/'normalization-invariance.json').write_text(json.dumps(norm,indent=2,allow_nan=False))
r=pd.DataFrame(rows);r.to_csv(O/'floor-program-sensitivity.tsv',sep='\t',index=False)
# Own-control genotype comparison, all times. Select references on WT/KO controls only.
ctrl=a[['PERK_WT_Control','PERK_KO_Control']];lb=np.log2(ctrl.where(ctrl>0));di=lb-lb.loc['Pmp22'];elig=(ctrl>=10).all(axis=1);distance=np.sqrt((di**2).sum(axis=1,skipna=False));box=di.abs().max(axis=1,skipna=False)<=1
traj=[];gs=[]
for time in [1,2,5,8]:
 wt=np.log2(a[f'PERK_WT_Tg{time}hr'].clip(lower=4)/a.PERK_WT_Control.clip(lower=4));ko=np.log2(a[f'PERK_KO_Tg{time}hr'].clip(lower=4)/a.PERK_KO_Control.clip(lower=4))
 t=pd.DataFrame({'time_h':time,'WT_log2FC':wt,'KO_log2FC':ko,'WT_minus_KO':wt-ko,'WT_control':ctrl.PERK_WT_Control,'KO_control':ctrl.PERK_KO_Control,'eligible_baseline10':elig,'baseline_box1':box});traj.append(t)
 for match in ['all','box1','nearest250']:
  ids=a.index[elig].difference(['Pmp22'])
  if match=='box1':ids=ids[box.loc[ids]]
  if match=='nearest250':ids=distance.loc[ids].sort_values(kind='stable').head(250).index
  s=stats(a.loc[ids],wt.loc[ids],ko.loc[ids],wt['Pmp22'],ko['Pmp22']);s.update(time_h=time,reference=match);gs.append(s)
t=pd.concat(traj);t.to_csv(O/'genotype-all-trajectories.tsv',sep='\t',index_label='gene');pd.DataFrame(gs).to_csv(O/'genotype-reference-summary.tsv',sep='\t',index=False)
t.loc[t.index.isin(['Pmp22','Atf4','Ddit3','Herpud1','Xbp1','Hspa5','Actb','Gapdh'])].to_csv(O/'genotype-controls.tsv',sep='\t',index_label='gene')
summary=dict(inputs=H,Pmp22_cluster=cl.loc['Pmp22'].to_dict(),source_shared_cluster_labels=len(f.index.intersection(cl.index)),cluster_unmatched_labels=[str(v) for v in f.index.difference(cl.index)],genotype_Pmp22=t.loc['Pmp22'].to_dict(orient='records'),genotype_matched_summary=[s for s in gs if s['reference']=='box1'],late_cluster_checks=r[(r.program=='Late_cluster')&(r['mode']=='baseline_only_clip4')].to_dict(orient='records'),primary_clip4=r[(r.time=='2h')&(r['mode']=='baseline_only_clip4')&(r.program=='all')&(r.match=='box1')].iloc[0].to_dict(),limits='All retrospective. Source clusters were selected from WT outcomes; conditional check only, not independent validation. Deposits retain sub4TPM values despite stated downstream threshold; explicit floor4 used in followup. n1 each, genotype clone/background confounding and no RNA/absolute synthesis.')
(O/'followup-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n');print(json.dumps(summary,indent=2,allow_nan=False))
