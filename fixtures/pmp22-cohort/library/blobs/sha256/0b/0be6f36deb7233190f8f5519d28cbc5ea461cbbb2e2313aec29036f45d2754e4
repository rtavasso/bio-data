"""Independent mTOR comparator test of an exploratory Nae1 antioxidant program.
Native XLSX values only; never evaluate formulas. Whole-study contrasts stay separate.
"""
from pathlib import Path
import json,hashlib,math
import numpy as np
import pandas as pd
from scipy import stats
from openpyxl import load_workbook
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
seal=json.loads((O/'antioxidant-seal-receipt.json').read_text());assert hashlib.sha256((O/'antioxidant-prediction-r001.json').read_bytes()).hexdigest()==seal['sha256']
ex=json.loads((O/'Figlia-extraction.json').read_text());p=Q/ex['output'];assert hashlib.sha256(p.read_bytes()).hexdigest()==ex['sha256']
wb=load_workbook(p,read_only=True,data_only=False)
A=['Nqo1','Hmox1','Gclc','Gclm','Osgin1'];M=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];REQ=A+M+['Pmp22']
PANEL={'antioxidant':A,'myelin':M,'Pmp22':['Pmp22'],'sterol':['Hmgcr','Hmgcs1','Fdft1','Sqle','Srebf2','Dhcr7','Dhcr24'],'immune':['Ptprc','Aif1','Csf1r','Tyrobp','Lyz2'],'fibroblast':['Col1a1','Col1a2','Dcn','Lum'],'other_regulators':['Nfe2l2','Keap1','Cul3','Slc7a11','Egr2','Jun','Sox2','Sox10','Nae1','Tsc1','Pten','Rptor']}
lookup={g:k for k,gg in PANEL.items() for g in gg}
CONTROL=[f'Dev{x}' for x in [1,2,3]];GROUPS={'TSC1KO':[f'Dev{x}' for x in [4,5,6]],'RaptorKO':[f'Dev{x}' for x in [7,8,9]],'PTENKO':[f'Dev{x}' for x in [10,11,12]]}
def interval(a,b):
 a=np.asarray(a,float);b=np.asarray(b,float);effect=float(a.mean()-b.mean());v=a.var(ddof=1)/len(a);w=b.var(ddof=1)/len(b);se=math.sqrt(v+w);df=(v+w)**2/(v*v/(len(a)-1)+w*w/(len(b)-1));r=float(stats.t.ppf(.975,df)*se);return dict(effect=effect,ci95=[effect-r,effect+r],df=df)
frames={};counts={};effects={};quality=[];mapping=[];rows=[];scores=[];sensitivity=[]
for group,cs in GROUPS.items():
 s=wb['Control vs '+group];it=s.iter_rows(values_only=True);h=next(it);rr=list(it);assert not any(isinstance(v,str) and v.startswith('=') for r in rr for v in r),'Formula present'
 d=pd.DataFrame(rr,columns=h);assert d.Identifier.is_unique
 d=d.set_index('gene_name',drop=False);duplicates=set(d.index[d.index.duplicated(False)]);d=d.loc[~d.index.duplicated(False)]
 C=d[[x+' [normalized count]' for x in CONTROL+cs]].apply(pd.to_numeric,errors='raise');C.columns=CONTROL+cs
 F=d[[x+' [FPKM]' for x in CONTROL+cs]].apply(pd.to_numeric,errors='raise');F.columns=CONTROL+cs
 assert np.isfinite(C.values).all() and (C.values>=0).all()
 log=np.log2(C+.5);e=pd.to_numeric(d['log2 Ratio'],errors='raise');present=d.isPresent.astype(str).str.upper().eq('TRUE')
 for g in REQ:
  ok=g in d.index
  quality.append(dict(study=group,gene=g,source_present=bool(ok),source_status=str(d.loc[g,'isPresent']) if ok else None,baseline_min=float(C.loc[g,CONTROL].min()) if ok else None,eligible=bool(ok and present[g] and (C.loc[g,CONTROL]>=10).all()),duplicate=g in duplicates))
 # Mapping inference audited against source effects, excluding every analysis panel.
 valid=present & (C[CONTROL].min(axis=1)>=10)&(C[cs].min(axis=1)>=10)&~d.index.isin(lookup)
 empirical=np.log2(C.loc[valid,cs].mean(axis=1)/C.loc[valid,CONTROL].mean(axis=1));diff=empirical-e.loc[valid]
 corr=float(empirical.corr(e.loc[valid]));agree=float(diff.abs().median());mapok=corr>.95 and agree<.2
 mapping.append(dict(group=group,genes=int(valid.sum()),correlation=corr,median_abs_difference=agree,map_corroborated=mapok,native_statuses=d.isPresent.astype(str).value_counts().to_dict(),rows_with_unique_symbols=len(d),duplicate_symbols=sorted(duplicates),interpretation='ENA numeric sample aliases plus source-contrast corroboration; no individual litter identity'))
 assert mapok,'No interpretation with failed source mapping'
 frames[group]=d;counts[group]=C;effects[group]=e
 for g in d.index.intersection(pd.Index(lookup)):
  ci=interval(log.loc[g,cs],log.loc[g,CONTROL]);rows.append(dict(study=group,panel=lookup[g],gene=g,source_effect=float(e[g]),recomputed_effect=ci['effect'],ci_low=ci['ci95'][0],ci_high=ci['ci95'][1],baseline_min=float(C.loc[g,CONTROL].min()),source_status=str(d.loc[g,'isPresent'])))
 d.to_csv(O/f'figlia-{group}-native.tsv',sep='\t',index=False)
 for panel,gg in PANEL.items():
  if not all(g in log.index and present[g] for g in gg):continue
  ss=log.loc[gg].mean();ci=interval(ss[cs],ss[CONTROL]);source_mean=float(e.loc[gg].mean())
  scores.append(dict(study=group,panel=panel,n_genes=len(gg),source_effect=source_mean,**ci))
  for sample,v in ss.items():sensitivity.append(dict(study=group,panel=panel,analysis='sample_score',unit=sample,value=float(v)))
  for omit in cs+CONTROL:
   a=[x for x in cs if x!=omit];b=[x for x in CONTROL if x!=omit];sensitivity.append(dict(study=group,panel=panel,analysis='leave_one_sample_out',unit=omit,value=float(ss[a].mean()-ss[b].mean())))
  ff=np.log2(F.loc[gg]+.5).mean();sensitivity.append(dict(study=group,panel=panel,analysis='source_FPKM',unit='',value=float(ff[cs].mean()-ff[CONTROL].mean())))
# Existing Nae1 output, explicitly reused new computation not independent source.
C=pd.read_csv(O/'nae1-all-expected-counts.tsv',sep='\t',index_col=0);sy=C.pop('symbol');full_library_sums=C.sum();Y=pd.read_csv(O/'nae1-all-log2normalized.tsv',sep='\t',index_col=0);Y.pop('symbol')
unique=~sy.duplicated(False)&sy.notna();excluded=sy.loc[~unique]
excluded.to_csv(O/'antioxidant-nae1-ambiguous-symbols.tsv',sep='\t')
assert not set(REQ)&set(excluded.dropna()),'Required feature ambiguous; locked test untestable'
C=C.loc[unique];Y=Y.loc[unique];C.index=sy.loc[unique];Y.index=sy.loc[unique]
assert C.index.is_unique
WT=[c for c in C if c.startswith('WT_')];KO=[c for c in C if c.startswith('KO_')];ne=Y[KO].mean(axis=1)-Y[WT].mean(axis=1);effects['Nae1KO']=ne
for g in REQ:quality.append(dict(study='Nae1KO',gene=g,source_present=g in C.index,source_status='no exported status flags',baseline_min=float(C.loc[g,WT].min()),eligible=bool((C.loc[g,WT]>=10).all()),duplicate=False))
for g in Y.index.intersection(pd.Index(lookup)):
 ci=interval(Y.loc[g,KO],Y.loc[g,WT]);rows.append(dict(study='Nae1KO',panel=lookup[g],gene=g,source_effect=float(ne[g]),recomputed_effect=ci['effect'],ci_low=ci['ci95'][0],ci_high=ci['ci95'][1],baseline_min=float(C.loc[g,WT].min()),source_status='no exported status flags'))
for panel,gg in PANEL.items():
 if not all(g in Y.index for g in gg):continue
 ss=Y.loc[gg].mean();ci=interval(ss[KO],ss[WT]);scores.append(dict(study='Nae1KO',panel=panel,n_genes=len(gg),source_effect=float(ne.loc[gg].mean()),**ci))
 for sample,v in ss.items():sensitivity.append(dict(study='Nae1KO',panel=panel,analysis='sample_score',unit=sample,value=float(v)))
 for omit in KO+WT:
  aa=[x for x in KO if x!=omit];bb=[x for x in WT if x!=omit];sensitivity.append(dict(study='Nae1KO',panel=panel,analysis='leave_one_sample_out',unit=omit,value=float(ss[aa].mean()-ss[bb].mean())))
 cpm=C.div(full_library_sums,axis=1)*1e6;ss=np.log2(cpm.loc[gg]+.5).mean();sensitivity.append(dict(study='Nae1KO',panel=panel,analysis='CPM',unit='',value=float(ss[KO].mean()-ss[WT].mean())))
for group,e in effects.items():
 for gene in A:sensitivity.append(dict(study=group,panel='antioxidant',analysis='leave_one_gene_out',unit=gene,value=float(e.loc[[g for g in A if g!=gene]].mean()) if all(g in e.index for g in A) else None))
qual=pd.DataFrame(quality);qual.to_csv(O/'antioxidant-eligibility.tsv',sep='\t',index=False)
pd.DataFrame(rows).to_csv(O/'antioxidant-gene-effects.tsv',sep='\t',index=False);pd.DataFrame(sensitivity).to_csv(O/'antioxidant-sensitivities.tsv',sep='\t',index=False)
(O/'antioxidant-source-mapping.json').write_text(json.dumps(mapping,indent=2));(O/'antioxidant-panel-scores.json').write_text(json.dumps(scores,indent=2,allow_nan=False))
required_studies=['Nae1KO','TSC1KO','PTENKO'];eligible=bool(qual[qual.study.isin(required_studies)].eligible.all())
ss={(r['study'],r['panel']):r['source_effect'] for r in scores}
criteria=dict(eligible=eligible,nae1_mean_gt1=ss.get(('Nae1KO','antioxidant'),-math.inf)>1,nae1_four_positive=int((ne.reindex(A)>0).sum())>=4)
for group in ['TSC1KO','PTENKO']:
 criteria[group+'_antioxidant_lt1']=ss.get((group,'antioxidant'),math.inf)<1
 criteria[group+'_separation_ge1']=ss.get(('Nae1KO','antioxidant'),-math.inf)-ss.get((group,'antioxidant'),math.inf)>=1
 criteria[group+'_pmp22_negative']=ss.get((group,'Pmp22'),math.inf)<0
 criteria[group+'_myelin_negative']=ss.get((group,'myelin'),math.inf)<0
# Broad shared feature response and source-defined mTOR program; descriptive genes are not replicates.
wide=pd.concat(effects,axis=1).dropna();wide=wide.loc[wide.index.notna()];wide['Nae1_minus_hyper_mTOR']=wide.Nae1KO-wide[['TSC1KO','PTENKO']].mean(axis=1);wide.to_csv(O/'antioxidant-shared-effects.tsv',sep='\t')
wide.corr(method='spearman').to_csv(O/'antioxidant-effect-correlations.tsv',sep='\t')
wide.nlargest(40,'Nae1_minus_hyper_mTOR').to_csv(O/'antioxidant-broad-divergences.tsv',sep='\t')
programs=[]
for name in ['mTORC1-induced genes','mTORC1-repressed genes']:
 data=list(wb[name].values);gg=[r[0] for r in data[1:] if r[0] in wide.index];sub=wide.loc[gg];sub.to_csv(O/('antioxidant-'+name.replace(' ','-')+'.tsv'),sep='\t');programs.append(dict(name=name,source_genes=len(data)-1,shared_genes=len(gg),median_effects=sub.median().to_dict()))
summary=dict(prediction_sha256=seal['sha256'],criteria=criteria,passes_locked_rule=all(criteria.values()),status='supported_in_scope' if all(criteria.values()) else ('contradicted' if eligible else 'untestable'),panel_scores=scores,shared_feature_count=len(wide),source_mtor_programs=programs,interpretation_limit='Comparative signature, not proof of NRF2 activity, cell autonomy, antioxidant mediation or novelty. Same three Figlia controls reused. P5/P7, drivers and composition differ; intervals conditional on sample map.',mapping='ENA numeric aliases corroborated by all-feature contrast agreement excluding tested panels; Dev prefix link remains inferred, not explicit ENA library name. Primary uses source contrast, sample estimates secondary.')
(O/'antioxidant-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(pd.DataFrame(rows).query('panel in ["antioxidant","Pmp22","other_regulators"]').to_string(index=False));print('MAPPING',mapping)
fig,axs=plt.subplots(1,2,figsize=(12,5));order=['Nae1KO','TSC1KO','PTENKO','RaptorKO'];d=pd.DataFrame(rows).pivot(index='gene',columns='study',values='source_effect').reindex(A+['Slc7a11','Nfe2l2','Pmp22']+M).reindex(columns=order);im=axs[0].imshow(d,aspect='auto',cmap='coolwarm',vmin=-3,vmax=3);axs[0].set(yticks=range(len(d)),yticklabels=d.index,xticks=range(4),xticklabels=order,title='Within-study RNA log2 response');fig.colorbar(im,ax=axs[0],label='log2 KO/control')
for k,panel in enumerate(['antioxidant','myelin','Pmp22']):
 sr=[next(a for a in scores if a['study']==g and a['panel']==panel) for g in order];xx=np.arange(4)+(k-1)*.18;yy=np.array([a['effect'] for a in sr]);er=np.array([[a['effect']-a['ci95'][0],a['ci95'][1]-a['effect']] for a in sr]).T;axs[1].errorbar(xx,yy,yerr=er,fmt='o',label=panel,capsize=3)
axs[1].axhline(0,color='grey',lw=.7);axs[1].set(xticks=range(4),xticklabels=order,ylabel='Mean sample log2 response; Welch 95% CI',title='Different sources, not a pooled experiment');axs[1].legend();fig.tight_layout();fig.savefig(O/'antioxidant-comparison.png',dpi=180);fig.savefig(O/'antioxidant-comparison.pdf');plt.close(fig)
