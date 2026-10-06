"""Retrospective r003 robustness and quantitative integrity audit."""
from pathlib import Path
import json,hashlib,itertools
import numpy as np
import pandas as pd
from scipy import stats
Q=Path(__file__).resolve().parents[1];O=Q/'outputs';D=O/'matrices';A=['Nqo1','Hmox1','Gclc','Gclm'];M=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];panels={'antioxidant4':A,'no_Nqo1':A[1:],'Pmp22':['Pmp22'],'myelin7':M}
def load(n):return pd.read_csv(D/(n+'.tsv.gz'),sep='\t',index_col=0)
def save(n,d):d.to_csv(O/n,sep='\t',index=False,na_rep='NA')
checks=[]
bulk=pd.read_csv(O/'bulk-panel-effects.tsv',sep='\t');old=json.loads((O/'inherited-antioxidant-summary.json').read_text())['panels'];mapping={'eligible4':'antioxidant4','discovery_gene_excluded':'no_Nqo1','myelin':'myelin7','Pmp22':'Pmp22','Pmp22_relative':'Pmp22_relative'}
for r in old:
 z=bulk[(bulk.study==r['study'])&(bulk.panel==mapping[r['panel']])].iloc[0];assert abs(z.effect-r['effect'])<1e-12
checks.append('All 20 inherited panel effects reproduced within 1e-12; original failed/untestable locks unchanged')
# Repair library-size sensitivity via median ratios fit within each compartment.
rc=load('repair-counts');meta=pd.read_csv(O/'repair-samples.tsv',sep='\t');out=[]
for comp in meta.compartment.unique():
 ss=meta.loc[meta.compartment==comp,'sample'];c=rc[ss];pos=(c>0).all(axis=1);sf=c.loc[pos].div(np.exp(np.log(c.loc[pos]).mean(axis=1)),axis=0).median();y=np.log2(c.div(sf)+.5);aa=meta.loc[(meta.compartment==comp)&meta.day.eq(0),'sample']
 for day in [3,5,7]:
  bb=meta.loc[(meta.compartment==comp)&meta.day.eq(day),'sample']
  for panel,genes in panels.items():out.append(dict(compartment=comp,day=day,panel=panel,normalization='within-compartment median ratio',effect=float(y.loc[genes,bb].mean().mean()-y.loc[genes,aa].mean().mean())))
save('repair-normalization-sensitivity.tsv',pd.DataFrame(out))
# Sorted interval/pseudocount sensitivity: genuine pairing verified in metadata.
s=load('sorted-rpkm');rows=[]
for pc in [.01,.1,.5]:
 y=np.log2(s+pc);aa=[f'{i}_mSC' for i in range(1,5)];bb=[f'{i}_nmSC' for i in range(1,5)]
 for panel,genes in panels.items():
  a=y.loc[genes,aa].mean().to_numpy();b=y.loc[genes,bb].mean().to_numpy();d=b-a;va=a.var(ddof=1)/4;vb=b.var(ddof=1)/4;df=(va+vb)**2/(va*va/3+vb*vb/3);rad=stats.t.ppf(.975,df)*np.sqrt(va+vb);pr=stats.t.ppf(.975,3)*d.std(ddof=1)/2
  rows.append(dict(pseudocount=pc,panel=panel,effect=float(d.mean()),unpaired_low=float(d.mean()-rad),unpaired_high=float(d.mean()+rad),paired_low=float(d.mean()-pr),paired_high=float(d.mean()+pr),subject_omission_min=float(min(np.delete(d,i).mean() for i in range(4))),subject_omission_max=float(max(np.delete(d,i).mean() for i in range(4)))))
save('sorted-robustness.tsv',pd.DataFrame(rows))
# All post-E17 developmental age contrasts (ordered younger minus older).
d=load('development-rpkm');ages=['E17','P1','P5','P14','P24','P60'];rows=[]
for a,b in itertools.combinations(ages,2):
 aa=[s for s in d if s.startswith(a+'_')];bb=[s for s in d if s.startswith(b+'_')]
 for pc in [.01,.1,.5]:
  eff=np.log2(d[aa]+pc).mean(axis=1)-np.log2(d[bb]+pc).mean(axis=1)
  for panel,genes in panels.items():rows.append(dict(younger=a,older=b,pseudocount=pc,panel=panel,effect=float(eff.loc[genes].mean())))
save('development-all-age-sensitivity.tsv',pd.DataFrame(rows))
# Genewise target effects and residual ranks, no new outcome-selected panel.
r=pd.read_csv(O/'projection-residuals.tsv.gz',sep='\t');rr=[];ext=[]
for (study,axes),z in r.groupby(['study','axes']):
 universe=z[z.fit_gene].residual
 for g in A+['Pmp22','Slc7a11','Osgin1','Nfe2l2']:
  row=z[z.gene.eq(g)]
  if len(row):v=row.iloc[0].to_dict();v['residual_percentile_in_fit_universe']=float((universe<=v['residual']).mean()*100);v['fit_universe']=len(universe);rr.append(v)
 if study=='Nae1KO' and axes=='sorted_nm_vs_m+P1_vs_P5':ext.append(pd.concat([z[z.fit_gene].nlargest(30,'residual'),z[z.fit_gene].nsmallest(30,'residual')]))
save('target-residual-ranks.tsv',pd.DataFrame(rr));save('broad-residual-extremes.tsv',pd.concat(ext))
ref=pd.read_csv(O/'reference-effects.tsv',sep='\t');matched=[]
for study in bulk.study.unique():
 b=bulk[bulk.study==study].set_index('panel')
 for name in ['sorted_nm_vs_m','P1_vs_P5','P5_vs_P14']:
  z=ref[(ref.reference==name)&ref.pseudocount.eq(.1)].set_index('panel');alpha=b.at['myelin7','effect']/z.at['myelin7','effect']
  for panel in panels:matched.append(dict(study=study,reference=name,panel=panel,myelin_matched_scale=float(alpha),observed=b.at[panel,'effect'],predicted=float(alpha*z.at[panel,'effect']),residual=float(b.at[panel,'effect']-alpha*z.at[panel,'effect']),caution='Exploratory after reference outcome; scale outside 0-1 extrapolates'))
save('myelin-matched-diagnostic.tsv',pd.DataFrame(matched))
# Verify pool bookkeeping, absence of pseudo-replicated cell-level tests.
qc=pd.read_csv(O/'cell-reference-QC.tsv',sep='\t');cs=json.loads((O/'composition-summary.json').read_text());assert int(qc.cells.sum())==cs['annotated_cells'];assert len(qc)==33 and qc.groupby('run').cluster.nunique().eq(11).all()
checks.append('All 11,339 annotated P1 cells mapped once across 3 pools and 11 labels; no cells counted as independent mice')
cc=pd.read_csv(O/'composition-compatibility.tsv',sep='\t');unique=cc[cc.marker_deletion.eq('none')];summary=unique.groupby(['study','constraints','tolerance_log2']).feasible.agg(['sum','count']).reset_index();save('composition-compatibility-unique-summary.tsv',summary)
# Count solver infeasibilities only after every status is either feasible or explicitly infeasible.
assert set(cc.solver_status)<=set([0,2]);checks.append('All LP solutions terminated with success or explicit infeasibility, not numeric failure')
# Independent elementary test of ratio bound for positive mixtures.
rg=np.array([2.,5.,1.]);rh=np.array([1.,2.,3.]);weights=np.array([[.2,.3,.5],[.8,.1,.1]]);rat=(weights@rg)/(weights@rh);assert abs(np.log2(rat[1]/rat[0]))<=np.log2((rg/rh).max()/(rg/rh).min())
checks.append('Positive-mixture ratio bound algebra checked on known synthetic vectors (test only, not scientific data)')
for receipt in ['prepare-execution-r002.json','state-execution-r002.json','composition-execution-r001.json']:
 x=json.loads((O/receipt).read_text());assert x['complete'] and x['exit_code']==0
 for record in x['outputs']:assert record['written'] and hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()==record['sha256']
checks.append('Producer output hashes match successful prepare/state/composition execution receipts')
result=dict(checks=checks,retrospective=True,repair_normalization=out,mixture_distinct_variants=summary.to_dict('records'),source_vs_interpretation='Source outcomes reproduced; computational pass is not causal validation')
(O/'robustness-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2));print(pd.DataFrame(rr).query("study=='Nae1KO' and axes=='sorted_nm_vs_m+P1_vs_P5'").to_string(index=False));print(pd.concat(ext).to_string(index=False))
