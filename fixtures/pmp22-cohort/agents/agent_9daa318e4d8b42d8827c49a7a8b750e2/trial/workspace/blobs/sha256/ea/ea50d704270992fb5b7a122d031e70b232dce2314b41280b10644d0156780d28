from pathlib import Path
import io,zipfile,json,hashlib
import openpyxl,numpy as np,pandas as pd
from scipy import stats
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/iteration';O=Q/'outputs/iteration';W=Q.parents[1]
inv=json.loads((O/'pten-input-objects.json').read_text());h=inv['mtor-supplements.zip']['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h
outer=zipfile.ZipFile(p);nested=outer.read('44321_2023_19_MOESM7_ESM.zip');z=zipfile.ZipFile(io.BytesIO(nested));rows=[];dups=[];maps=[]
for panel,name,width in [('7A','Figure7/7A_DatamRNAexpression.xlsx',4),('7B','Figure7/7B_DatamRNAexpression.xlsx',2)]:
 b=z.read(name);w=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=False);s=w.worksheets[0];v=list(s.values)
 assert not any(c.data_type=='f' for row in s for c in row),'Formula encountered, do not execute or substitute cached values'
 for j in range(s.max_column):
  gene=v[0][j-j%width];group=v[1][j]
  for i,row in enumerate(v[2:],start=3):
   x=row[j];rows.append({'panel':panel,'gene':gene.lower(),'group':group,'source_row':i,'source_col':j+1,'value':x,'status':'blank_not_measured_zero' if x is None else 'source_numeric'})
 # row-vector equality across groups is a source QC observation, not proof of animal identity.
 for g in range(width):
  for i in range(2,len(v)):
   vals=tuple(v[i][j+g] for j in range(0,s.max_column,width))
   if all(x is not None for x in vals):maps.append({'panel':panel,'group':v[1][g],'source_row':i+1,'vector':vals})
for i,a in enumerate(maps):
 for b in maps[i+1:]:
  if a['panel']==b['panel'] and a['group']!=b['group'] and a['vector']==b['vector']:dups.append({'a':a,'b':b})
d=pd.DataFrame(rows);d.to_csv(O/'pten-source-cells.tsv',sep='\t',index=False);out=[]
for panel,contrasts in [('7A',[('CMT1A','WT'),('PTENhKO','WT'),('PTENhKOxCMT1A','CMT1A'),('PTENhKOxCMT1A','WT')]),('7B',[('HNPP','WT')])]:
 for gene in d[d.panel==panel].gene.unique():
  for a,b in contrasts:
   for sensitivity in (['all','drop_HNPP_duplicate_row8','drop_WT_duplicate_row6'] if panel=='7B' else ['all']):
    sub=d[(d.panel==panel)&(d.gene==gene)&(d.status=='source_numeric')]
    if sensitivity=='drop_HNPP_duplicate_row8':sub=sub[~((sub.group=='HNPP')&(sub.source_row==8))]
    if sensitivity=='drop_WT_duplicate_row6':sub=sub[~((sub.group=='WT')&(sub.source_row==6))]
    x=sub[sub.group==a].value.to_numpy(float);y=sub[sub.group==b].value.to_numpy(float);assert (x>0).all() and (y>0).all();lx,ly=np.log2(x),np.log2(y)
    va,vb=lx.var(ddof=1)/len(x),ly.var(ddof=1)/len(y);df=(va+vb)**2/(va*va/(len(x)-1)+vb*vb/(len(y)-1));delta=stats.t.ppf(.975,df)*np.sqrt(va+vb);effect=lx.mean()-ly.mean()
    out.append({'panel':panel,'gene':gene,'a':a,'b':b,'sensitivity':sensitivity,'n_a':len(x),'n_b':len(y),'arithmetic_mean_a':x.mean(),'arithmetic_mean_b':y.mean(),'ratio_means':x.mean()/y.mean(),'log2_geometric_effect':effect,'descriptive_ci_low':effect-delta,'descriptive_ci_high':effect+delta})
r=pd.DataFrame(out);r.to_csv(O/'pten-contrasts.tsv',sep='\t',index=False)
summary={'source':'PMC10940316 Source Data Figure7 native xlsx in supplementary ZIP','source_status':'All filled cells numeric; no formulas. Native blank cells retained separately.','sample_counts':d[d.status=='source_numeric'].groupby(['panel','gene','group']).size().reset_index(name='n').to_dict(orient='records'),'cross_group_exact_six_gene_vectors':dups,'limitations':['7A source supplies4 WT,5 PTENhKO,5 CMT1A,4 double mutant, but Figure7 legend states5 double mutant. Missing5th not imputed.','7B six-gene vector WT worksheet row6 exactly equals HNPP row8, so animal independence cannot be established from table. No arbitrary correction; removal of either vector is only sensitivity.','Source reports normalized qPCR with Rplp0/Ppia controls; Ct/animal IDs absent; no pairing inferred across genes or panels.','No PMP22 RNA/protein endpoint after PTEN intervention here; no reverse transcriptional feedback established.','Selected six genes, not a broad assay. Descriptive CI assumes independent values and is not a remedy for source unit uncertainty.']}
(O/'pten-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps({'duplicates':dups,'limitations':summary['limitations']},indent=2));print(r[(r.panel=='7A')&(r.a=='PTENhKOxCMT1A')&(r.b=='CMT1A')].to_string(index=False))
