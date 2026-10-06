"""Execute checkpoint-r002 developmental/state and existing-bulk sensitivities.
No causal adjustment claims; reference resampling uses subjects, not genes.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1]; O=Q/'outputs'; D=O/'matrices'
rng=np.random.default_rng(290926)
A=['Nqo1','Hmox1','Gclc','Gclm']; M=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal']
PAN={'antioxidant4':A,'no_Nqo1':A[1:],'Pmp22':['Pmp22'],'myelin7':M,'immune':['Ptprc','Aif1','Csf1r','Tyrobp','Lyz2'],'fibroblast':['Col1a1','Col1a2','Dcn','Lum'],'endothelial':['Pecam1','Kdr','Cdh5'],'proliferation':['Mki67','Top2a','Pcna','Cdk1'],'immature':['Ngfr','Sox2','Jun','Gap43'],'SC_identity':['Sox10','S100b','Erbb3']}
TARGET=A+['Pmp22','Slc7a11','Osgin1','Nfe2l2']+M
inputs=[]
def load(n):
 p=D/(n+'.tsv.gz'); inputs.append({'path':str(p.relative_to(Q)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});return pd.read_csv(p,sep='\t',index_col=0)
def save(n,d):d.to_csv(O/n,sep='\t',index=False,na_rep='NA')
def js(n,d):(O/n).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def interval(x,y,paired=False):
 x=np.asarray(x);y=np.asarray(y);e=float(x.mean()-y.mean())
 if paired:
  se=(x-y).std(ddof=1)/np.sqrt(len(x)); df=len(x)-1
 else:
  v=x.var(ddof=1)/len(x);w=y.var(ddof=1)/len(y);se=np.sqrt(v+w);df=(v+w)**2/(v*v/(len(x)-1)+w*w/(len(y)-1)) if v+w else 1
 r=float(stats.t.ppf(.975,df)*se);return e,e-r,e+r

dev=load('development-rpkm');sort=load('sorted-rpkm'); n=load('nae1-counts');ny=load('nae1-log2'); f=load('figlia-counts');fy=load('figlia-log2')
studies={'Nae1KO':(n,ny,[s for s in n if s.startswith('WT')],[s for s in n if s.startswith('KO')])}
for group,idx in [('TSC1KO',[4,5,6]),('PTENKO',[10,11,12]),('RaptorKO',[7,8,9])]:studies[group]=(f,fy,['Dev1','Dev2','Dev3'],['Dev'+str(i) for i in idx])
refs={'sorted_nm_vs_m':(sort,[str(i)+'_mSC' for i in range(1,5)],[str(i)+'_nmSC' for i in range(1,5)],True)}
for a,b in [('P5','P1'),('P14','P5'),('P60','E17'),('P24','P14'),('P60','P24')]:refs[b+'_vs_'+a]=(dev,[s for s in dev if s.startswith(a+'_')],[s for s in dev if s.startswith(b+'_')],False)
reference_rows=[];ref_effects={};targets=[]
for name,(d,aa,bb,paired) in refs.items():
 for pc in [.01,.1,.5]:
  y=np.log2(d+pc);eff=y[bb].mean(axis=1)-y[aa].mean(axis=1)
  if pc==.1:ref_effects[name]=eff
  for panel,genes in {**PAN,**{g:[g] for g in TARGET}}.items():
   present=[g for g in genes if g in y.index]
   if len(present)!=len(genes):continue
   s=y.loc[genes].mean();e,lo,hi=interval(s[bb],s[aa],paired)
   reference_rows.append(dict(reference=name,pseudocount=pc,panel=panel,effect=e,ci_low=lo,ci_high=hi,paired=paired,mean_rpkm_control=float(d.loc[genes,aa].mean().mean()),mean_rpkm_alternative=float(d.loc[genes,bb].mean().mean()),ratio_arithmetic_mean=float(np.log2((d.loc[genes,bb].mean(axis=1)+pc)/(d.loc[genes,aa].mean(axis=1)+pc)).mean())))
  if pc==.1:
   for g in TARGET:
    if g in d.index:
     for sample in aa+bb:targets.append(dict(reference=name,gene=g,sample=sample,rpkm=d.at[g,sample],low_in_both=bool(d.loc[g,aa].mean()<1 and d.loc[g,bb].mean()<1)))
ref=pd.DataFrame(reference_rows);save('reference-effects.tsv',ref);save('reference-target-cells.tsv',pd.DataFrame(targets));pd.DataFrame(ref_effects).to_csv(O/'reference-all-effects.tsv.gz',sep='\t',compression='gzip')

# Original exposed contrasts and same-study genotype/proxy sensitivity, one proxy at a time.
score_rows=[];bulk_rows=[];adjust=[];stable_rows=[]
for study,(c,y,aa,bb) in studies.items():
 sdict={k:y.loc[[g for g in gg if g in y.index]].mean() for k,gg in PAN.items()}
 sdict['Pmp22_relative']=sdict['Pmp22']-sdict['myelin7']
 for panel,s in sdict.items():
  e,lo,hi=interval(s[bb],s[aa]);bulk_rows.append(dict(study=study,panel=panel,effect=e,ci_low=lo,ci_high=hi))
  for sample in aa+bb:score_rows.append(dict(study=study,panel=panel,sample=sample,group='control' if sample in aa else 'KO',score=s[sample],genes_used=';'.join(g for g in PAN.get(panel,M+['Pmp22']) if g in y.index)))
 for proxy in ['immune','fibroblast','endothelial','proliferation','immature','myelin7','SC_identity']:
  cov=sdict[proxy][aa+bb].to_numpy();cov=(cov-cov.mean())/cov.std(ddof=1);gen=np.r_[np.zeros(len(aa)),np.ones(len(bb))];X=np.column_stack([np.ones(len(gen)),gen,cov]);r=float(np.corrcoef(cov,gen)[0,1]);overlap=max(cov[:len(aa)].min(),cov[len(aa):].min())<=min(cov[:len(aa)].max(),cov[len(aa):].max())
  for panel in ['antioxidant4','no_Nqo1','Pmp22']:
   outcome=sdict[panel][aa+bb].to_numpy();coef=np.linalg.lstsq(X,outcome,rcond=None)[0];leaves=[]
   for i in range(len(gen)):
    take=np.arange(len(gen))!=i
    if np.linalg.matrix_rank(X[take])==3:leaves.append(float(np.linalg.lstsq(X[take],outcome[take],rcond=None)[0][1]))
   adjust.append(dict(study=study,panel=panel,proxy=proxy,genotype_coefficient=coef[1],genotype_proxy_r=r,vif=1/(1-r*r),overlap=bool(overlap),rank=int(np.linalg.matrix_rank(X)),condition=float(np.linalg.cond(X)),leave_min=min(leaves),leave_max=max(leaves),causal=False))
 # Reference-defined stable genes, selected without KO outcomes.
 common=y.index.intersection(dev.index).intersection(sort.index)
 dl=np.log2(dev.loc[common,[s for s in dev if s.startswith(('P1_','P5_','P14_'))]]+.1)
 sl=np.log2(sort.loc[common]+.1)
 stable=common[(dl.max(axis=1)-dl.min(axis=1)<1)&(sl.max(axis=1)-sl.min(axis=1)<1)&(dev.loc[common].mean(axis=1)>=5)&(sort.loc[common].mean(axis=1)>=5)&(c.loc[common,aa].mean(axis=1)>=50)&(y.loc[common,aa].std(axis=1)<.35)]
 stable=stable.difference(TARGET)
 assert len(stable)>=10
 baseline=y.loc[stable].mean()
 for panel in ['antioxidant4','no_Nqo1','Pmp22']:
  score=sdict[panel]-baseline;e,lo,hi=interval(score[bb],score[aa]);stable_rows.append(dict(study=study,panel=panel,stable_gene_count=len(stable),effect=e,ci_low=lo,ci_high=hi))
 pd.Series(stable).to_csv(O/(study+'-reference-stable-genes.tsv'),sep='\t',index=False,header=['gene'])
save('bulk-panel-effects.tsv',pd.DataFrame(bulk_rows));save('bulk-sample-scores.tsv',pd.DataFrame(score_rows));save('bulk-adjustment-sensitivity.tsv',pd.DataFrame(adjust));save('stable-ratio-sensitivity.tsv',pd.DataFrame(stable_rows))

# Broad reference projection. Target outcomes withheld from fitting, not from study.
projections=[];residual_rows=[];bootstrap=[]
axes=[['sorted_nm_vs_m'],['P1_vs_P5'],['P5_vs_P14'],['sorted_nm_vs_m','P1_vs_P5']]
for study,(c,y,aa,bb) in studies.items():
 effect=y[bb].mean(axis=1)-y[aa].mean(axis=1)
 for axis in axes:
  allgenes=effect.index
  for key in axis:allgenes=allgenes.intersection(ref_effects[key].index)
  fit=allgenes[(c.loc[allgenes,aa].mean(axis=1)>=10)]
  for key in axis:
   rd,ra,rb,_=refs[key];fit=fit[rd.loc[fit,ra+rb].mean(axis=1)>=1]
  fit=fit.difference(TARGET)
  Xall=np.column_stack([np.ones(len(allgenes))]+[ref_effects[k].loc[allgenes].to_numpy() for k in axis]);pos=allgenes.get_indexer(fit);X=Xall[pos];v=effect.loc[fit].to_numpy();coef=np.linalg.lstsq(X,v,rcond=None)[0];pred=Xall@coef;res=effect.loc[allgenes]-pred
  r2=1-np.square(v-X@coef).sum()/np.square(v-v.mean()).sum()
  projections.append(dict(study=study,axes='+'.join(axis),fit_genes=len(fit),r2=float(r2),coefficients=coef.tolist(),spearman=[float(stats.spearmanr(X[:,i+1],v).statistic) for i in range(len(axis))],rmse=float(np.sqrt(np.mean((v-X@coef)**2)))))
  for g in allgenes:residual_rows.append(dict(study=study,axes='+'.join(axis),gene=g,observed=effect[g],predicted=pred[allgenes.get_loc(g)],residual=res[g],fit_gene=g in fit))
  # Reference uncertainty only; preserve subject pairing for sorted gates.
  wanted=allgenes.intersection(TARGET);idx=allgenes.get_indexer(wanted);stored=[]
  cached=[]
  for key in axis:
   rd,ra,rb,paired=refs[key];cached.append((np.log2(rd.loc[allgenes,ra].to_numpy()+.1),np.log2(rd.loc[allgenes,rb].to_numpy()+.1),paired))
  for b in range(250):
   xx=[np.ones(len(allgenes))]
   for left,right,paired in cached:
    ia=rng.integers(0,left.shape[1],left.shape[1]);ib=ia if paired else rng.integers(0,right.shape[1],right.shape[1]);xx.append(right[:,ib].mean(axis=1)-left[:,ia].mean(axis=1))
   bx=np.column_stack(xx);bc=np.linalg.lstsq(bx[pos],v,rcond=None)[0];stored.append(effect.loc[wanted].to_numpy()-bx[idx]@bc)
  stored=np.asarray(stored)
  for panel,genes in {k:PAN[k] for k in ['antioxidant4','no_Nqo1','Pmp22','myelin7']}.items():
   ii=wanted.get_indexer(genes);assert (ii>=0).all();br=stored[:,ii].mean(axis=1);bootstrap.append(dict(study=study,axes='+'.join(axis),panel=panel,observed=float(effect.loc[genes].mean()),predicted=float((effect-res).loc[genes].mean()),residual=float(res.loc[genes].mean()),reference_bootstrap_lo=float(np.quantile(br,.025)),reference_bootstrap_hi=float(np.quantile(br,.975)),resamples=250))
js('projection-fit.json',projections);save('projection-residuals.tsv.gz',pd.DataFrame(residual_rows));save('projection-panel-sensitivity.tsv',pd.DataFrame(bootstrap))

# Repair reference includes both compartments; pooling and cross-species limits retained.
repair=load('repair-log2cpm');rc=load('repair-counts');meta=json.loads((O/'GSE177037-design-summary.json').read_text());rm=[]
for r in meta:
 if 'Sample_title' not in r:continue
 title=r['Sample_title'][0];sample=r['Sample_description'][0];comp='purified_SC' if title.startswith('Schwann') else 'whole_nerve';day=0 if 'Uncrushed' in title else int(title.split('d post-crush')[0].split()[-1]);rm.append(dict(sample=sample,compartment=comp,day=day,title=title))
rm=pd.DataFrame(rm);save('repair-samples.tsv',rm);repair_rows=[];repair_broad=[]
for comp in rm.compartment.unique():
 aa=rm.loc[(rm.compartment==comp)&rm.day.eq(0),'sample'].tolist()
 for day in [3,5,7]:
  bb=rm.loc[(rm.compartment==comp)&rm.day.eq(day),'sample'].tolist();assert len(aa)==len(bb)==2
  eff=repair[bb].mean(axis=1)-repair[aa].mean(axis=1)
  for panel,genes in {**{k:PAN[k] for k in ['antioxidant4','no_Nqo1','Pmp22','myelin7']},**{g:[g] for g in A}}.items():
   s=repair.loc[genes].mean();repair_rows.append(dict(compartment=comp,day=day,panel=panel,effect=float(s[bb].mean()-s[aa].mean()),min_count=float(rc.loc[genes,aa+bb].min().min())))
  for study,(c,y,a,b) in studies.items():
   common=eff.index.intersection(y.index);common=common[(rc.loc[common,aa].mean(axis=1)>=10)&(c.loc[common,a].mean(axis=1)>=10)]
   v=y.loc[common,b].mean(axis=1)-y.loc[common,a].mean(axis=1);repair_broad.append(dict(compartment=comp,day=day,study=study,genes=len(common),same_symbol_not_full_orthology=True,spearman=float(stats.spearmanr(eff.loc[common],v).statistic)))
save('repair-effects.tsv',pd.DataFrame(repair_rows));save('repair-broad-concordance.tsv',pd.DataFrame(repair_broad))

# Reference whole transcriptome PCA and developmental trajectories.
fig,axs=plt.subplots(2,2,figsize=(12,9));pca_rows=[]
for ax,(label,d) in zip(axs[0],[('development',dev),('sorted',sort)]):
 z=np.log2(d.loc[d.mean(axis=1)>=1]+.1);z=z.sub(z.mean(axis=1),axis=0);u,s,v=np.linalg.svd(z.to_numpy().T,full_matrices=False);sc=u[:,:2]*s[:2]
 for i,sample in enumerate(z):ax.scatter(*sc[i]);ax.annotate(sample,sc[i],fontsize=6);pca_rows.append(dict(dataset=label,sample=sample,PC1=sc[i,0],PC2=sc[i,1],variance_PC1=s[0]**2/(s*s).sum(),variance_PC2=s[1]**2/(s*s).sum()))
 ax.set_title(label+' reference PCA')
ages=['E13','E17','P1','P5','P14','P24','P60']
for g in A+['Pmp22']:
 yy=[np.log2(dev.loc[g,[s for s in dev if s.startswith(a+'_')]]+.1).mean() for a in ages];axs[1,0].plot(ages,yy,marker='o',label=g)
axs[1,0].legend();axs[1,0].set_ylabel('mean log2 RPKM + 0.1')
bt=pd.DataFrame(bootstrap);b=bt[(bt.study=='Nae1KO')&(bt.panel=='antioxidant4')];axs[1,1].barh(b['axes'],b.residual);axs[1,1].axvline(1,color='grey');axs[1,1].set_title('Nae1 antioxidant residual after reference projection');fig.tight_layout();fig.savefig(O/'state-reference-analysis.png',dpi=160);plt.close(fig);save('reference-PCA.tsv',pd.DataFrame(pca_rows))
js('state-analysis-summary.json',dict(inputs=inputs,panels=PAN,bulk=bulk_rows,reference_primary=ref[(ref.pseudocount==.1)&ref.panel.isin(['antioxidant4','no_Nqo1','Pmp22','myelin7'])].to_dict('records'),projections=bootstrap,projection_fit=projections,repair=pd.DataFrame(repair_rows).query("panel in ['antioxidant4','no_Nqo1','Pmp22','myelin7']").to_dict('records'),limitations=['Retrospective bulk; new reference axes checkpointed before outcomes','Genes and cell states are not biological replicates','Reference bootstrap quantifies reference-subject sampling only, not causal or cross-study uncertainty','Same Figlia controls reused once; cohorts not pooled','RPKM/normalized counts/CPM are relative; no promoter or absolute RNA inference']))
print(ref[(ref.pseudocount==.1)&ref.panel.isin(['antioxidant4','no_Nqo1','Pmp22','myelin7'])].to_string(index=False));print(bt.to_string(index=False));print(pd.DataFrame(repair_rows).to_string(index=False))
