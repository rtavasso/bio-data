"""Prespecified confounder checks and explicitly exploratory sensitivity; cannot rescue primary tests."""
from pathlib import Path
import json,io,gzip
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';D=Q/'inputs/specific';W=Q.parents[1];fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0]
L=pd.read_csv(O/'discovery-log2CPM.tsv',sep='\t',index_col=0);A=pd.read_csv(O/'zeb2-log2-expression.tsv',sep='\t',index_col=0);H=pd.read_csv(O/'hdac3-FPKM.tsv',sep='\t',index_col=0);screen=pd.read_csv(O/'discovery-all-gene-screen.tsv',sep='\t');markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];cand=['Ppp6r1','Gtf2f1','Hck'];familiar=['Egr2','Sox10','Jun','Runx1','Runx3','Yy1','Ezh2','Tead1','Hdac3','Zeb2'];immune=['Ptprc','Aif1','Lyz2','Csf1r','Tyrobp'];fibro=['Col1a1','Col1a2','Dcn'];endothelial=['Pecam1','Kdr'];states=np.repeat([0,3,5,7],2)
screen[screen.gene.isin(cand+familiar)].to_csv(O/'familiar-regulator-comparison.tsv',sep='\t',index=False)
# Source-matched full count matrices and compartment controls.
r=json.loads((D/'fetch-discovery.json').read_text());h=r['blob'];raw=pd.read_csv(W/'blobs/sha256'/h[:2]/h,compression='gzip',sep='\t',index_col=0);ids=raw.index.str.split('_');ok=[len(p)==2 and p[0]==p[1] for p in ids];x=raw.loc[ok].copy();x.index=[p[-1] for p,k in zip(ids,ok) if k];alllog=np.log2(x.div(raw.sum())*1e6+.5)
sc=list(L.columns);wn=['IL6174','IL6175','IL6178','IL6179','IL6182','IL6183','IL6186','IL6187'];comp=[]
for day in [0,3,5,7]:
 for g in cand+markers+['Pmp22']+immune+fibro+endothelial:
  if g not in alllog.index:continue
  ix=np.where(states==day)[0];sv=alllog.loc[g,[sc[i] for i in ix]].mean();wv=alllog.loc[g,[wn[i] for i in ix]].mean();comp.append({'gene':g,'day':day,'SC_mean_log2CPM':sv,'whole_nerve_mean_log2CPM':wv,'whole_nerve_minus_SC':wv-sv})
pd.DataFrame(comp).to_csv(O/'compartment-enrichment.tsv',sep='\t',index=False)
# Candidate slopes after competing measured programs, descriptive with low residual df.
conf=[]
for name,F,groups in [('discovery',L,states),('Zeb2_validation',A,np.array([1,1,1,0,0,0]))]:
 M=F.loc[markers].mean().values;y=F.loc['Pmp22'].values;I=F.loc[[g for g in immune if g in F.index]].mean().values;fib=F.loc[[g for g in fibro if g in F.index]].mean().values;T=np.eye(len(np.unique(groups)))[np.searchsorted(np.unique(groups),groups)]
 for control,C in [('myelin',np.column_stack([np.ones(len(M)),M])),('myelin+state',np.column_stack([T,M])),('myelin+immune',np.column_stack([np.ones(len(M)),M,I])),('myelin+fibroblast',np.column_stack([np.ones(len(M)),M,fib]))]:
  yr=y-C@fit(C,y)
  for g in cand:
   z=F.loc[g].values;zr=z-C@fit(C,z);conf.append({'dataset':name,'controls':control,'candidate':g,'partial_r':np.corrcoef(yr,zr)[0,1],'slope':(zr@yr)/(zr@zr),'residual_df':len(M)-np.linalg.matrix_rank(C)-1})
pd.DataFrame(conf).to_csv(O/'confounder-adjustment.tsv',sep='\t',index=False)
# Freeze candidate choice; refit coefficients only in discovery under each alternative score, then transfer. Post-lock sensitivities.
sets={'primary7':markers,'core4':['Mpz','Mbp','Mag','Prx']};sets.update({'omit_'+g:[m for m in markers if m!=g] for g in markers});sens=[]
for score,ms in sets.items():
 M=L.loc[ms].mean().values;y=L.loc['Pmp22'].values;B=np.column_stack([np.ones(len(M)),M]);bb=fit(B,y)
 for context,F,mode in [('Zeb2',A,'array'),('Hdac3_cnp',H[['cnp-ko','cnp-ctrl']],'FPKM'),('Hdac3_dhh',H[['dhh-ko','dhh-ctrl']],'FPKM')]:
  FF=F if mode=='array' else np.log2(F+.5);d=FF.iloc[:,:3].mean(1)-FF.iloc[:,3:].mean(1) if mode=='array' else FF.iloc[:,0]-FF.iloc[:,1];dm=d.loc[ms].mean();dy=d.loc['Pmp22'];base=bb[1]*dm
  for g in cand:
   co=fit(np.column_stack([B,L.loc[g].values]),y);pred=co[1]*dm+co[2]*d.loc[g];sens.append({'context':context,'score':score,'candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'baseline_prediction':base,'augmented_prediction':pred,'SSE_ratio':(dy-pred)**2/(dy-base)**2})
pd.DataFrame(sens).to_csv(O/'marker-sensitivity.tsv',sep='\t',index=False)
# Cross-endpoint specificity: each myelin target removed from score; no independent claim from training data.
targets=[]
for target in ['Pmp22']+markers:
 ms=[g for g in markers if g!=target];M=L.loc[ms].mean().values;y=L.loc[target].values;B=np.column_stack([np.ones(8),M]);yr=y-B@fit(B,y)
 for g in cand:
  X=np.column_stack([B,L.loc[g].values]);zr=L.loc[g].values-B@fit(B,L.loc[g].values);pred=np.zeros(8);base=np.zeros(8)
  for st in [0,3,5,7]:
   tr=states!=st;te=~tr;pred[te]=X[te]@fit(X[tr],y[tr]);base[te]=B[te]@fit(B[tr],y[tr])
  targets.append({'target':target,'candidate':g,'partial_r':np.corrcoef(zr,yr)[0,1],'LOTO_SSE_ratio':((y-pred)**2).sum()/((y-base)**2).sum()})
pd.DataFrame(targets).to_csv(O/'alternate-myelin-targets.tsv',sep='\t',index=False)
# Native HDAC3 source rows: zeros are deposited measurements; source statuses/locus retained.
source=[]
for key in ['cnp-ctrl','cnp-ko','dhh-ctrl','dhh-ko']:
 rec=json.loads((D/f'fetch-hdac3-{key}.json').read_text());h=rec['blob'];f=pd.read_csv(W/'blobs/sha256'/h[:2]/h,compression='gzip',sep='\t');z=f.loc[f.gene_short_name.isin(markers+cand+['Pmp22'])].copy();z.insert(0,'sample',key);source.append(z)
pd.concat(source).to_csv(O/'hdac3-native-panel.tsv',sep='\t',index=False)
# Pseudocount impacts: strict no-pseudocount impossible for full panel with zero Mpz; leave-out explicitly sensitivity.
pseud=[];lock=json.loads((O/'prediction-r002.json').read_text());models=json.loads(lock['prediction'])['frozen_models'];b0=json.loads(lock['baseline_model'])['coefficients'][1]
for pc in [.1,.5,1.]:
 LH=np.log2(H+pc)
 for cre in ['cnp','dhh']:
  d=LH[cre+'-ko']-LH[cre+'-ctrl'];dy=d.loc['Pmp22'];dm=d.loc[markers].mean();base=b0*dm
  for model in models:
   g=model['gene'];pred=model['myelin_beta']*dm+model['gene_beta']*d.loc[g];pseud.append({'pseudocount':pc,'context':cre,'candidate':g,'baseline_prediction':base,'augmented_prediction':pred,'observed_Pmp22':dy,'SSE_ratio':(dy-pred)**2/(dy-base)**2})
pd.DataFrame(pseud).to_csv(O/'hdac3-pseudocount-sensitivity.tsv',sep='\t',index=False)
# Broad perturbation patterns, controls and retained endpoints.
AA=A.iloc[:,:3].mean(1)-A.iloc[:,3:].mean(1);out=pd.DataFrame({'Zeb2_log2_change':AA,'Hdac3_Cnp_log2_change':np.log2((H['cnp-ko']+.5)/(H['cnp-ctrl']+.5)),'Hdac3_Dhh_log2_change':np.log2((H['dhh-ko']+.5)/(H['dhh-ctrl']+.5))});out.loc[out.index.isin(cand+familiar+markers+immune+fibro+['Pmp22'])].to_csv(O/'perturbation-biological-panel.tsv',sep='\t',na_rep='NA')
summary={'scope':'Prespecified alternative checks; sensitivity coefficients refitted only to discovery. Does not replace frozen primary validation.','excluded_discovery_feature_fraction_of_library':((raw.loc[~np.array(ok)].sum())/raw.sum()).to_dict(),'max_discovery_logCPM_difference_full_vs_mapped_denominator':float((alllog[sc].loc[L.index]-L).abs().max().max()),'Hck_whole_nerve_minus_SC':pd.DataFrame(comp).query("gene=='Hck'").to_dict(orient='records'),'candidate_time_adjustment':pd.DataFrame(conf).query("dataset=='discovery' and controls=='myelin+state'").to_dict(orient='records'),'HDAC3_Mpz_zero_caution':'Native Mpz=0 in Cnp control, Cnp KO, Dhh control; 21157.6 FPKM Dhh KO, status OK. Full-panel Dhh score is dominated by this source anomaly; do not infer huge generalized myelination. Omit-Mpz sensitivity required. Gene-level zero not promoter output.','primary_conclusion':'No selected candidate passes sealed primary test; secondary context fits cannot rescue.','source_units':'Rat RSEM expected counts, mouse log2RMA, mouse Cufflinks FPKM; gene-level steady-state measures.'}
(O/'alternatives-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(pd.DataFrame(sens).query("score=='omit_Mpz'").to_string(index=False))
