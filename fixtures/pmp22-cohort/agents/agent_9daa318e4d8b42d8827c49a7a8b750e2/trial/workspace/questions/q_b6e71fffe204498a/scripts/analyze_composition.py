"""P1 source-annotated pseudobulks and fixed-profile mixture compatibility.
LP tests existence, not measured fractions. Reference transcript/gene assay bias
constant across types cancels in within-gene, anchor-normalized fold constraints.
Missing pathogenic states and age/assay-dependent biases remain outside the null.
"""
from pathlib import Path
import json,hashlib,gzip
import numpy as np
import pandas as pd
from scipy.io import mmread
from scipy.optimize import linprog
from scipy import stats
from xls_values import read_xls
Q=Path(__file__).resolve().parents[1];W=Q.parents[1];O=Q/'outputs';D=O/'matrices'
A=['Nqo1','Hmox1','Gclc','Gclm'];MY=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];anchors=['Actb','Rplp0','Ppia','Hprt','Tbp'];exclude=A+MY+['Pmp22','Slc7a11','Osgin1','Nfe2l2']+anchors
inputs=[]
def source(name):
 r=json.loads((Q/'inputs/managed'/(name+'.fetch.json')).read_text());h=r['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;inputs.append(dict(name=name,blob=h,asset=r['asset_revision']));return p
def save(name,d):d.to_csv(O/name,sep='\t',index=False,na_rep='NA')
s=read_xls(source('elife-58591-supp2.xls'))['10X_P1 related to Figure 6'];assert not s['formulas'] and not s['errors'];labels=pd.DataFrame(s['rows'][1:],columns=s['rows'][0]).set_index('Cell');assert labels.index.is_unique
counts={};qc=[];detection={};gene_map=None
for run,gsm in [(1,'GSM4113877'),(2,'GSM4113878'),(3,'GSM4113879')]:
 stem=gsm+'_10X_P1_'+str(run)+'_';genes=pd.read_csv(source(stem+'genes.tsv.gz'),sep='\t',compression='gzip',header=None,names=['id','symbol']);bar=pd.read_csv(source(stem+'barcodes.tsv.gz'),sep='\t',compression='gzip',header=None)[0]
 with gzip.open(source(stem+'matrix.mtx.gz'),'rb') as f:mat=mmread(f).tocsc()
 assert mat.shape==(len(genes),len(bar));assert (mat.data>=0).all() and np.equal(mat.data,np.floor(mat.data)).all()
 # Barcode suffix -1 denotes GEM well, while v1/v2/v3 is source run prefix.
 names=['v'+str(run)+'_'+b.removesuffix('-1') for b in bar];lab=labels.reindex(names);selected=lab.Cluster.notna().to_numpy();assert len(labels.loc[labels.index.str.startswith('v'+str(run)+'_')])==selected.sum()
 if gene_map is None:gene_map=genes
 else:assert genes.equals(gene_map)
 for typ in sorted(lab.Cluster.dropna().unique()):
  take=(lab.Cluster==typ).to_numpy();v=np.asarray(mat[:,take].sum(axis=1)).ravel();key='v'+str(run)+'|'+typ;counts[key]=v;detection[key]=np.asarray((mat[:,take]>0).sum(axis=1)).ravel()/take.sum();qc.append(dict(run=run,cluster=typ,cells=int(take.sum()),UMI=int(v.sum()),median_UMI=float(np.median(np.asarray(mat[:,take].sum(axis=0)).ravel())),input_cells=len(bar),unlabelled_cells=int((~selected).sum())))
C=pd.DataFrame(counts,index=gene_map.id);tot=C.sum();unamb=~gene_map.symbol.duplicated(False)&gene_map.symbol.notna();C=C.loc[unamb.to_numpy()];C.index=gene_map.loc[unamb,'symbol'];detect=pd.DataFrame(detection,index=gene_map.id).loc[unamb.to_numpy()];detect.index=C.index;profiles=C.div(tot)*1e6
C.to_csv(O/'cell-pseudobulk-counts.tsv.gz',sep='\t',compression='gzip');profiles.to_csv(O/'cell-pseudobulk-cpm.tsv.gz',sep='\t',compression='gzip');save('cell-reference-QC.tsv',pd.DataFrame(qc));rows=[]
for g in exclude:
 if g in C.index:
  for col in C:rows.append(dict(gene=g,run=col.split('|')[0],cluster=col.split('|')[1],UMI=int(C.at[g,col]),CPM=profiles.at[g,col],detection_fraction=detect.at[g,col]))
save('cell-target-expression.tsv',pd.DataFrame(rows))
# Paired pool-level immature/proliferating vs promyelinating Schwann states.
staterows=[]
for alt in ['iSC','prol. SC']:
 for panel,gg in {'antioxidant4':A,'no_Nqo1':A[1:],'Pmp22':['Pmp22'],'myelin7':MY,**{g:[g] for g in A}}.items():
  left=np.log2(profiles[[f'v{i}|pmSC' for i in [1,2,3]]].loc[gg]+.5).mean().to_numpy();right=np.log2(profiles[[f'v{i}|{alt}' for i in [1,2,3]]].loc[gg]+.5).mean().to_numpy();delta=right-left;radius=stats.t.ppf(.975,2)*delta.std(ddof=1)/np.sqrt(3);staterows.append(dict(alternative=alt,control='pmSC',panel=panel,effect=float(delta.mean()),pool_ci_low=float(delta.mean()-radius),pool_ci_high=float(delta.mean()+radius),n_independent_pools=3))
save('cell-SC-state-effects.tsv',pd.DataFrame(staterows))
# Reference average per type gives equal weight to independent pools, not cells.
R=profiles.T.groupby(profiles.columns.str.split('|').str[1]).mean().T
# Broad identity markers selected WITHOUT bulk outcomes. Ten enriched genes/type,
# expression >=5 CPM and at least 1 log2 above every other type.
markers=[]
for typ in R:
 other=R.drop(columns=typ).max(axis=1);specificity=np.log2((R[typ]+.5)/(other+.5));eligible=specificity[(R[typ]>=5)&(specificity>=1)&~specificity.index.isin(exclude)].nlargest(10)
 for gene,value in eligible.items():markers.append(dict(cluster=typ,gene=gene,specificity_log2=float(value),CPM=float(R.at[gene,typ])))
markers=pd.DataFrame(markers);save('cell-reference-identity-markers.tsv',markers)
ny=pd.read_csv(D/'nae1-log2.tsv.gz',sep='\t',index_col=0);nc=pd.read_csv(D/'nae1-counts.tsv.gz',sep='\t',index_col=0);fy=pd.read_csv(D/'figlia-log2.tsv.gz',sep='\t',index_col=0);fc=pd.read_csv(D/'figlia-counts.tsv.gz',sep='\t',index_col=0)
studies={'Nae1KO':(ny,nc,[x for x in ny if x.startswith('WT')],[x for x in ny if x.startswith('KO')])}
for group,idx in [('TSC1KO',[4,5,6]),('PTENKO',[10,11,12]),('RaptorKO',[7,8,9])]:studies[group]=(fy,fc,['Dev1','Dev2','Dev3'],['Dev'+str(i) for i in idx])
variants={'equal_pool_mean':R}
for omit in [1,2,3]:
 p=profiles.loc[:,~profiles.columns.str.startswith('v'+str(omit)+'|')];variants['omit_pool_'+str(omit)]=p.T.groupby(p.columns.str.split('|').str[1]).mean().T
for run in [1,2,3]:
 p=profiles.filter(regex='^v'+str(run)+r'\|').copy();p.columns=p.columns.str.split('|').str[1];variants['pool_'+str(run)]=p
bounds=[];compat=[];marker_effect=[]
# In a positive mixture the gene/anchor ratio lies within the reference type
# ratios; its possible between-mixture log2 change cannot exceed that range.
for study,(y,c,aa,bb) in studies.items():
 eff=y[bb].mean(axis=1)-y[aa].mean(axis=1)
 candidates=sorted(set(markers.gene)&set(y.index));candidates=[g for g in candidates if c.loc[g,aa+bb].mean()>=10]
 for g in candidates:marker_effect.append(dict(study=study,gene=g,log2FC=eff[g],reference_type=';'.join(markers.loc[markers.gene==g,'cluster'])))
 for variant,r in variants.items():
  for anchor in anchors:
   # Do not fill a genuinely unmeasured/zero reference row. Require positive.
   assert (r.loc[anchor]>0).all()
   ratio=r.div(r.loc[anchor],axis=1)
   for g in A+['Pmp22']:
    obs=float(eff[g]-eff[anchor]);vals=ratio.loc[g];valid=bool((vals>0).all());width=float(np.log2(vals.max()/vals.min())) if valid else None
    bounds.append(dict(study=study,variant=variant,anchor=anchor,gene=g,observed_logratio_change=obs,max_absolute_composition_change=width,outside_bound=bool(abs(obs)>width) if valid else None,min_type=vals.idxmin(),max_type=vals.idxmax(),zero_profile_present=not valid))
   # LP weights are anchor-RNA contributions, NOT measured cell fractions.
   k=len(r.columns);eq=np.zeros((2,2*k));eq[0,:k]=1;eq[1,k:]=1
   for deletion in ['none','immune','fibroblast'] if variant=='equal_pool_mean' else ['none']:
    selected=[g for g in candidates if not (deletion=='immune' and g in set(markers.loc[markers.cluster=='IC','gene'])) and not (deletion=='fibroblast' and g in set(markers.loc[markers.cluster.isin(['EnC','EpC','PnC','prol. Fb','FbRel*']),'gene']))]
    for tol in [.5,1.0]:
     for targetset in ['markers_only','markers_plus_antioxidants','antioxidants_only']:
      gg=selected if targetset=='markers_only' else selected+A if targetset=='markers_plus_antioxidants' else A
      gg=sorted(set(gg));B=[]
      for g in gg:
       rr=ratio.loc[g].to_numpy();rr=rr/max(rr.max(),1e-12);lo=2**float(eff[g]-eff[anchor]-tol);hi=2**float(eff[g]-eff[anchor]+tol);B.extend([np.r_[-hi*rr,rr],np.r_[lo*rr,-rr]])
      fit=linprog(np.zeros(2*k),A_ub=np.array(B),b_ub=np.zeros(len(B)),A_eq=eq,b_eq=np.ones(2),bounds=(0,None),method='highs')
      compat.append(dict(study=study,variant=variant,anchor=anchor,marker_deletion=deletion,tolerance_log2=tol,constraints=targetset,genes=len(gg),feasible=bool(fit.success),solver_status=int(fit.status),note='Existence test for fixed reference profiles, not fraction estimation'))
save('composition-logratio-bounds.tsv',pd.DataFrame(bounds));save('composition-compatibility.tsv',pd.DataFrame(compat));save('cell-identity-marker-bulk-effects.tsv',pd.DataFrame(marker_effect))
summary=dict(inputs=inputs,annotated_cells=len(labels),independent_biological_pools=3,cell_types=list(R.columns),markers_per_type=markers.groupby('cluster').size().to_dict(),SC_state_effects=staterows,profile_unit='UMI sums within source labelled cluster/run, divided by all mapped UMIs; equal-pool mean for between-type profiles',assumptions=['Fixed P1 cell-type profiles; no pathogenic cell state permitted','Within-gene assay effects constant across source cell types; not established for bulk versus 10x','Anchor-normalized logfold constraints tolerate 0.5 or 1.0 log2 per gene','All 11 annotated types included, permitting arbitrarily large mixture shifts; no tissue fraction assumed'],limits=['P1 is not P7 and lacks mature myelinating-cell capture','P1 FACS depleted SC; cluster frequencies cannot estimate tissue composition','Feasibility does not establish real mixtures; infeasibility rejects only the reference-restricted null','No estimates of absolute cell abundance or absolute RNA output'],compatibility_counts=pd.DataFrame(compat).groupby(['study','constraints','tolerance_log2']).feasible.agg(['sum','count']).reset_index().to_dict('records'))
(O/'composition-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
print(json.dumps(summary,indent=2));print(pd.DataFrame(bounds).query("study=='Nae1KO' and variant=='equal_pool_mean'").to_string(index=False))
