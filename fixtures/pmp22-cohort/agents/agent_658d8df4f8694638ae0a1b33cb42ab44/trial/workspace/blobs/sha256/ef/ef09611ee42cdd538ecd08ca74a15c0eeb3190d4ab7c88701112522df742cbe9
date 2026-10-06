"""Sealed Pmp22 RNA transfer test plus explicitly exploratory whole-transcriptome QC.
Reads only exact immutable processed RSEM assets. No raw read analysis.
"""
from pathlib import Path
import json,gzip,re,itertools,hashlib,math
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream';W=Q.parents[1]
MARKERS=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal']; REQUIRED=['Pmp22']+MARKERS
seal=json.loads((O/'prediction-seal-receipt.json').read_text());assert hashlib.sha256((O/'prediction-r001.json').read_bytes()).hexdigest()==seal['sha256']
records=sorted(json.loads((I/'rna-fetch-receipts.json').read_text()),key=lambda a:a['name'])
raw={};meta=[];ids=None;source=[]
for a in records:
 h=a['receipt']['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h
 sample=a['name'].split('_',1)[1].split('.genes')[0];group=sample.split('_')[0]
 with gzip.open(p,'rt') as f:d=pd.read_csv(f,sep='\t',dtype=str,keep_default_na=False)
 assert d.gene_id.is_unique
 if ids is None:ids=d.gene_id.tolist()
 assert d.gene_id.tolist()==ids
 symbols=d.gene_id.str.split('_',n=1).str[1]
 assert symbols.notna().all()
 d=d.set_index('gene_id');raw[sample]=d
 for gid in d.index[symbols.isin(REQUIRED).to_numpy()]:source.append(dict(sample=sample,group=group,gene_id=gid,symbol=gid.split('_',1)[1],**d.loc[gid].to_dict()))
 meta.append(dict(sample=sample,group=group,asset=a['receipt']['asset_revision'],blob=h,source=a['name']))
pd.DataFrame(meta).to_csv(O/'nae1-samples.tsv',sep='\t',index=False)
pd.DataFrame(source).to_csv(O/'nae1-required-source-cells.tsv',sep='\t',index=False)
C=pd.DataFrame({s:pd.to_numeric(d.expected_count,errors='raise') for s,d in raw.items()})
TPM=pd.DataFrame({s:pd.to_numeric(d.TPM,errors='raise') for s,d in raw.items()})
LENGTH=pd.DataFrame({s:pd.to_numeric(d.effective_length,errors='raise') for s,d in raw.items()})
assert np.isfinite(C.values).all() and (C.values>=0).all()
symbol=pd.Series([g.split('_',1)[1] for g in C.index],index=C.index,name='symbol')
map_rows=[];sel={};eligible=True
for g in REQUIRED:
 hits=symbol.index[symbol.eq(g)].tolist();ok=len(hits)==1
 if ok:sel[g]=hits[0];ok=bool((C.loc[hits[0]]>=10).all())
 map_rows.append(dict(symbol=g,source_ids=';'.join(hits),eligible=ok,minimum_count=float(C.loc[hits[0]].min()) if len(hits)==1 else None))
 eligible &= ok
pd.DataFrame(map_rows).to_csv(O/'nae1-required-eligibility.tsv',sep='\t',index=False)
status_cols=sorted({c for d in raw.values() for c in d.columns if 'status' in c.lower() or 'flag' in c.lower()})
assert not status_cols,'Need explicit source flag interpretation before continuing'
assert eligible,'Locked required panel untestable: inspect eligibility file; do not reduce panel'
WT=[s for s in C if s.startswith('WT_')];KO=[s for s in C if s.startswith('KO_')];assert len(WT)==len(KO)==4
pos=(C>0).all(axis=1);gm=np.exp(np.log(C.loc[pos]).mean(axis=1));sf=C.loc[pos].div(gm,axis=0).median();N=C.div(sf,axis=1);CPM=C.div(C.sum(),axis=1)*1e6;Y=np.log2(N+0.5)
C.assign(symbol=symbol).to_csv(O/'nae1-all-expected-counts.tsv',sep='\t');Y.assign(symbol=symbol).to_csv(O/'nae1-all-log2normalized.tsv',sep='\t')
# Difference statistic exactly as sealed: pseudocount on raw expected counts.
rawlogs=np.log2(C.loc[[sel[g] for g in REQUIRED]]+0.5);rawlogs.index=REQUIRED
R=rawlogs.loc['Pmp22']-rawlogs.loc[MARKERS].mean();primary=float(R[KO].mean()-R[WT].mean())
def effect_ci(a,b):
 a=np.asarray(a,float);b=np.asarray(b,float);va=a.var(ddof=1)/len(a);vb=b.var(ddof=1)/len(b);se=math.sqrt(va+vb);df=(va+vb)**2/(va**2/(len(a)-1)+vb**2/(len(b)-1));delta=float(a.mean()-b.mean());rad=float(stats.t.ppf(.975,df)*se);return dict(effect=delta,se=se,df=df,ci95=[delta-rad,delta+rad])
ci=effect_ci(R[KO],R[WT]);perms=[]
for inds in itertools.combinations(range(8),4):
 inds=list(inds);others=[x for x in range(8) if x not in inds];perms.append(float(R.iloc[inds].mean()-R.iloc[others].mean()))
perm_p=float(np.mean(np.abs(perms)>=abs(primary)-1e-12))
G=Y.loc[[sel[g] for g in REQUIRED]].copy();G.index=REQUIRED
target=float(G.loc['Pmp22',KO].mean()-G.loc['Pmp22',WT].mean());program=float(G.loc[MARKERS,KO].mean().mean()-G.loc[MARKERS,WT].mean().mean())
passed=target<0 and program<0 and primary>=1 and ci['ci95'][0]>0
pd.DataFrame(dict(sample=R.index,group=['KO' if s in KO else 'WT' for s in R.index],target_minus_markers=R.values,pmp22_log2normalized=G.loc['Pmp22'].values,marker_mean_log2normalized=G.loc[MARKERS].mean().values)).to_csv(O/'nae1-primary-per-sample.tsv',sep='\t',index=False)
# Sensitivity only. Markers are not replaced in the primary analysis.
sens=[]
for name,M in [('raw_expected_count',C),('median_ratio',N),('CPM',CPM),('source_TPM',TPM)]:
 z=np.log2(M.loc[[sel[g] for g in REQUIRED]]+.5);z.index=REQUIRED;r=z.loc['Pmp22']-z.loc[MARKERS].mean();sens.append(dict(analysis=name,delta=float(r[KO].mean()-r[WT].mean())))
for s in R.index:
 a=[x for x in KO if x!=s];b=[x for x in WT if x!=s];sens.append(dict(analysis='leave_out_'+s,delta=float(R[a].mean()-R[b].mean())))
for g in MARKERS+['core4']:
 panel=[m for m in MARKERS if m!=g] if g!='core4' else ['Mpz','Mbp','Mag','Prx'];r=rawlogs.loc['Pmp22']-rawlogs.loc[panel].mean();sens.append(dict(analysis='omit_'+g if g!='core4' else 'core4',delta=float(r[KO].mean()-r[WT].mean())))
r=R; sens.append(dict(analysis='L_labels_only_not_litter_adjustment',delta=float(r[[s for s in KO if '_L' in s]].mean()-r[[s for s in WT if '_L' in s]].mean())))
pd.DataFrame(sens).to_csv(O/'nae1-sensitivities.tsv',sep='\t',index=False)
pd.DataFrame([dict(KO=a,WT=b,delta=float(R[a]-R[b])) for a in KO for b in WT]).to_csv(O/'nae1-pairwise.tsv',sep='\t',index=False)
# Broad exploration. No selection on regulatory annotation; no genome-wide p-value claims.
expressed=((C>=10).sum(axis=1)>=4)&(N.mean(axis=1)>=20)
E=Y.loc[expressed]; effects=E[KO].mean(axis=1)-E[WT].mean(axis=1)
all_effects=pd.DataFrame(dict(symbol=symbol.loc[E.index],mean_WT_normalized=N.loc[E.index,WT].mean(axis=1),mean_KO_normalized=N.loc[E.index,KO].mean(axis=1),log2FC=effects,minimum_expected=C.loc[E.index].min(axis=1),min_pairwise=[float((E.loc[g,KO].to_numpy()[:,None]-E.loc[g,WT].to_numpy()[None,:]).min()) for g in E.index],max_pairwise=[float((E.loc[g,KO].to_numpy()[:,None]-E.loc[g,WT].to_numpy()[None,:]).max()) for g in E.index]))
all_effects.sort_values('log2FC').to_csv(O/'nae1-all-effects.tsv',sep='\t');pd.concat([all_effects.nsmallest(30,'log2FC'),all_effects.nlargest(30,'log2FC')]).to_csv(O/'nae1-extremes.tsv',sep='\t')
center=E.to_numpy().T-E.to_numpy().mean(axis=1);u,s,vh=np.linalg.svd(center,full_matrices=False);scores=u[:,:3]*s[:3];pca=pd.DataFrame(scores,index=E.columns,columns=['PC1','PC2','PC3']);pca['group']=['KO' if x in KO else 'WT' for x in pca.index];pca.to_csv(O/'nae1-PCA.tsv',sep='\t');E.corr().to_csv(O/'nae1-sample-correlations.tsv',sep='\t')
controls={'myelin':MARKERS+['Pmp22'],'regulators':['Nae1','Egr2','Jun','Sox2','Sox10','Zeb2','Rptor','Rheb','Tsc1','Tsc2','Yap1','Wwtr1','Tead1','Nedd8','Uba3'],'immune':['Ptprc','Aif1','Csf1r','Tyrobp','Lyz2'],'fibroblast':['Col1a1','Col1a2','Dcn','Lum'],'endothelial':['Pecam1','Kdr','Cdh5'],'sterol':['Hmgcr','Hmgcs1','Fdft1','Sqle','Srebf2','Dhcr7','Dhcr24']}
rows=[]
for panel,genes in controls.items():
 for g in genes:
  hits=symbol.index[symbol.eq(g)].tolist()
  if len(hits)==1:
   gid=hits[0];ef=effect_ci(Y.loc[gid,KO],Y.loc[gid,WT]);rows.append(dict(panel=panel,symbol=g,gene_id=gid,log2FC=ef['effect'],ci_low=ef['ci95'][0],ci_high=ef['ci95'][1],minimum_count=float(C.loc[gid].min()),mean_WT=float(N.loc[gid,WT].mean()),mean_KO=float(N.loc[gid,KO].mean()),effective_length_ratio=float(LENGTH.loc[gid,KO].mean()/LENGTH.loc[gid,WT].mean()) if LENGTH.loc[gid,WT].mean()>0 else None))
PD=pd.DataFrame(rows);PD.to_csv(O/'nae1-control-panels.tsv',sep='\t',index=False)
# Baseline-abundance-matched reference is descriptive, not added biological replication.
tid=sel['Pmp22'];base=N[WT].mean(axis=1);match=expressed & base.between(base[tid]/2,base[tid]*2) & ~symbol.isin(REQUIRED)
refs=all_effects.loc[match.reindex(all_effects.index)];refs.to_csv(O/'nae1-target-abundance-references.tsv',sep='\t')
summary=dict(question=Q.name,prediction_sha256=seal['sha256'],eligibility_pass=bool(eligible),status_columns=status_cols,source_semantics='RSEM fractional expected counts, TPM, FPKM; symbol suffix native in GENCODE.vM15 source IDs; no source quality flags exported',mapping_note='Native source identifier suffix directly supplies symbols; no guessed ortholog or obsolete platform mapping required. One exact native feature per required symbol.',rows=len(C),expressed_exploratory=int(expressed.sum()),positive_all_samples_for_normalization=int(pos.sum()),size_factors=sf.to_dict(),library_sums=C.sum().to_dict(),pmp22_log2FC=target,marker_mean_log2FC=program,deltaR=primary,deltaR_uncertainty=ci,permutation_two_sided_p=perm_p,permutation_assignments=len(perms),passes_locked_rule=bool(passed),interpretation='supported transfer in source' if passed else 'does not validate locked relative-preservation transfer',reference_count=len(refs),reference_effect_median=float(refs.log2FC.median()) if len(refs) else None,pmp22_effect_percentile=float((refs.log2FC<=target).mean()*100) if len(refs) else None,pca_fraction=(s*s/(s*s).sum()).tolist(),prior_exposure='source mechanistic findings exposed; target quantitative outcomes first inspected after seal; not fully blinded; separate experiments/ages do not establish direct causation',protein_limitation='No eligible quantitative protein export established; methods and caption ages conflict. No RNA-protein rate inferred.')
(O/'nae1-RNA-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
fig,axs=plt.subplots(1,3,figsize=(14,4.5))
for group,color in [('WT','#365b96'),('KO','#b04d3d')]:
 sub=pca[pca.group.eq(group)];axs[0].scatter(sub.PC1,sub.PC2,label=group,color=color)
 for name,row in sub.iterrows():axs[0].annotate(name,(row.PC1,row.PC2),fontsize=7)
axs[0].set(xlabel='PC1',ylabel='PC2',title='Exploratory transcriptome PCA');axs[0].legend()
for k,gg in enumerate(['WT','KO']):
 a=WT if gg=='WT' else KO;axs[1].scatter(np.repeat(k,len(a)),R[a]);axs[1].plot([k-.15,k+.15],[R[a].mean()]*2,color='black')
axs[1].set(xticks=[0,1],xticklabels=['WT','Nae1 cKO'],ylabel='log2 Pmp22 - mean log2 myelin markers',title=f'Locked DeltaR {primary:.2f}; 95% CI {ci["ci95"][0]:.2f}, {ci["ci95"][1]:.2f}')
pp=PD[PD.symbol.isin(REQUIRED)].set_index('symbol').loc[REQUIRED];axs[2].errorbar(pp.log2FC,np.arange(len(pp)),xerr=np.vstack([pp.log2FC-pp.ci_low,pp.ci_high-pp.log2FC]),fmt='o');axs[2].axvline(0,color='grey',lw=.7);axs[2].set(yticks=np.arange(len(pp)),yticklabels=pp.index,xlabel='KO/WT RNA log2 difference',title='Gene effects; Welch 95% intervals');fig.tight_layout();fig.savefig(O/'nae1-RNA.png',dpi=180);fig.savefig(O/'nae1-RNA.pdf');plt.close(fig)
print(json.dumps(summary,indent=2));print(PD.to_string(index=False));print('BROAD EXTREMES');print(pd.concat([all_effects.nsmallest(12,'log2FC'),all_effects.nlargest(12,'log2FC')]).to_string())
