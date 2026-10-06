"""Post-hoc eligible antioxidant panel; does not rescue the five-gene lock."""
from pathlib import Path
import json,math
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/upstream'
P=['Nqo1','Hmox1','Gclc','Gclm'];M=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal']
def ci(a,b):
 v=a.var(ddof=1)/len(a);w=b.var(ddof=1)/len(b);d=float(a.mean()-b.mean());df=(v+w)**2/(v*v/(len(a)-1)+w*w/(len(b)-1));r=float(stats.t.ppf(.975,df)*np.sqrt(v+w));return dict(effect=d,ci95=[d-r,d+r])
C=pd.read_csv(O/'nae1-all-expected-counts.tsv',sep='\t',index_col=0);sy=C.pop('symbol');tot=C.sum();Y=pd.read_csv(O/'nae1-all-log2normalized.tsv',sep='\t',index_col=0);Y.pop('symbol');unique=~sy.duplicated(False)&sy.notna();C=C.loc[unique];Y=Y.loc[unique];C.index=sy.loc[unique];Y.index=sy.loc[unique]
WT=[s for s in C if s.startswith('WT_')];KO=[s for s in C if s.startswith('KO_')]
D={'Nae1KO':(C,Y,WT,KO,np.log2(C.div(tot,axis=1)*1e6+.5))}
for group,nums in [('TSC1KO',[4,5,6]),('PTENKO',[10,11,12]),('RaptorKO',[7,8,9])]:
 d=pd.read_csv(O/f'figlia-{group}-native.tsv',sep='\t',index_col='gene_name');a=[f'Dev{x}' for x in [1,2,3]];b=[f'Dev{x}' for x in nums];c=d[[s+' [normalized count]' for s in a+b]].copy();c.columns=a+b;f=d[[s+' [FPKM]' for s in a+b]].copy();f.columns=a+b;D[group]=(c,np.log2(c+.5),a,b,np.log2(f+.5))
rows=[];sourcecells=[];per=[]
for group,(c,y,a,b,alt) in D.items():
 for gene in P+['Slc7a11','Nfe2l2','Pmp22']+M:
  for sample in a+b:sourcecells.append(dict(study=group,gene=gene,sample=sample,group='KO' if sample in b else 'Control',count=float(c.loc[gene,sample]),log2amount=float(y.loc[gene,sample])))
 for panel,gg in [('eligible4',P),('discovery_gene_excluded',[g for g in P if g!='Nqo1']),('myelin',M),('Pmp22',['Pmp22']),('Pmp22_relative',M+['Pmp22'])]:
  if panel in ['eligible4','discovery_gene_excluded']:assert (c.loc[gg,a]>=10).all().all()
  s=y.loc[gg].mean() if panel!='Pmp22_relative' else y.loc['Pmp22']-y.loc[M].mean();v=ci(s[b],s[a]);aa=alt.loc[gg].mean() if panel!='Pmp22_relative' else alt.loc['Pmp22']-alt.loc[M].mean();pairs=s[b].to_numpy()[:,None]-s[a].to_numpy()[None,:]
  leave=[float(s[[i for i in b if i!=sample]].mean()-s[[i for i in a if i!=sample]].mean()) for sample in a+b]
  geneleave=[float((y.loc[[g for g in gg if g!=gene],b].mean()-0).mean()-y.loc[[g for g in gg if g!=gene],a].mean().mean()) for gene in gg] if len(gg)>1 and panel!='Pmp22_relative' else []
  rows.append(dict(study=group,panel=panel,n_control=len(a),n_KO=len(b),**v,alternative_normalization=float(aa[b].mean()-aa[a].mean()),all_pairwise_range=[float(pairs.min()),float(pairs.max())],sample_omission_range=[min(leave),max(leave)],gene_omission_range=[min(geneleave),max(geneleave)] if geneleave else None))
  for sample,value in s.items():per.append(dict(study=group,panel=panel,sample=sample,group='KO' if sample in b else 'Control',score=float(value)))
pd.DataFrame(sourcecells).to_csv(O/'antioxidant-posthoc-source-cells.tsv',sep='\t',index=False);pd.DataFrame(per).to_csv(O/'antioxidant-posthoc-scores.tsv',sep='\t',index=False)
wide=pd.read_csv(O/'antioxidant-shared-effects.tsv',sep='\t',index_col=0);broad=dict(shared=len(wide),spearman=wide[['Nae1KO','TSC1KO','PTENKO','RaptorKO']].corr(method='spearman').to_dict(),panel_ranks={g:dict(residual=float(wide.loc[g,'Nae1_minus_hyper_mTOR']),percentile=float((wide.Nae1_minus_hyper_mTOR<=wide.loc[g,'Nae1_minus_hyper_mTOR']).mean()*100)) for g in P+['Slc7a11','Pmp22']})
summary=dict(status='retrospective_exploratory_not_validation',original_lock='untestable due Osgin1 baseline floor; unchanged',panels=rows,broad=broad,interpretation='Eligible antioxidant response distinguishes these source contrasts, not NRF2-mediated PMP22 regulation. Gene-set selection/revision post hoc; cell mixture, age and driver remain competing explanations.')
(O/'antioxidant-posthoc-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2))
fig,ax=plt.subplots(figsize=(9,5));order=list(D)
for k,panel in enumerate(['eligible4','discovery_gene_excluded','myelin','Pmp22']):
 rr=[next(r for r in rows if r['study']==g and r['panel']==panel) for g in order];yy=np.array([r['effect'] for r in rr]);err=np.array([[r['effect']-r['ci95'][0],r['ci95'][1]-r['effect']] for r in rr]).T;ax.errorbar(np.arange(4)+(k-1.5)*.16,yy,yerr=err,fmt='o',capsize=3,label=panel)
ax.axhline(0,c='grey',lw=.7);ax.set(xticks=range(4),xticklabels=order,ylabel='Within-study mean RNA log2 response',title='Exploratory eligible panel; five-gene lock untestable');ax.legend(fontsize=9);fig.tight_layout();fig.savefig(O/'antioxidant-posthoc.png',dpi=180);fig.savefig(O/'antioxidant-posthoc.pdf');plt.close(fig)
