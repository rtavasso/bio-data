from pathlib import Path
import json
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/specific';O=Q/'outputs/specific';W=Q.parents[1]
markers=['Mbp','Mag','Prx','Plp1','Cnp','Mal'];panel=['Pmp22','Mpz']+markers+['Ppp6r1','Gtf2f1','Hck','Egr2','Sox10','Jun','Zeb2'];rows=[];tables={};qc=[]
for key in ['control','ko']:
 r=json.loads((D/f'fetch-zeb2-rnaseq-{key}.json').read_text());h=r['blob'];f=pd.read_csv(W/'blobs/sha256'/h[:2]/h,compression='gzip',sep='\t');f.columns=f.columns.str.strip()
 for col in f.select_dtypes('object'):f[col]=f[col].str.strip()
 z=f[f.gene_id.isin(panel)].copy();z.insert(0,'source_file',key);rows.append(z);a={}
 for g,t in z.groupby('gene_id'):
  a[g]=float(t.FPKM.sum()) if t.tracking_id.is_unique and t.FPKM_status.eq('OK').all() else np.nan
 tables[key]=pd.Series(a);qc.append({'source_file':key,'rows':len(f),'nonunique_tracking_id_rows':int(f.tracking_id.duplicated(keep=False).sum()),'status_counts':f.FPKM_status.value_counts().to_dict(),'aggregation':'Sum FPKM within panel gene only if all statuses OK and transcript IDs unique within gene; otherwise unavailable. This is not count summation or a promoter readout.'})
pd.concat(rows).to_csv(O/'zeb2-rnaseq-transcript-source-panel.tsv',sep='\t',index=False);T=pd.DataFrame(tables);T['log2_KO_over_control_pc0.5']=np.log2((T.ko+.5)/(T.control+.5));G=pd.read_csv(O/'zeb2-rnaseq-native-panel.tsv',sep='\t',index_col=0);T['cuffdiff_summary_log2_change']=G.calculated_log2_change;T.to_csv(O/'zeb2-representation-comparison.tsv',sep='\t',na_rep='NA')
L=pd.read_csv(O/'discovery-log2CPM.tsv',sep='\t',index_col=0);M=L.loc[markers].mean().values;y=L.loc['Pmp22'].values;B=np.column_stack([np.ones(len(M)),M]);fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0];b=fit(B,y);delta=T['log2_KO_over_control_pc0.5'];dm=delta.loc[markers].mean();dy=delta.loc['Pmp22'];base=b[1]*dm;out=[]
assert T.loc[markers+['Pmp22','Ppp6r1','Gtf2f1','Hck'],['control','ko']].notna().all().all()
for g in ['Ppp6r1','Gtf2f1','Hck']:
 c=fit(np.column_stack([B,L.loc[g]]),y);pred=c[1]*dm+c[2]*delta.loc[g];out.append({'candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'delta_candidate':delta.loc[g],'baseline_prediction':base,'augmented_prediction':pred,'SSE_ratio':(dy-pred)**2/(dy-base)**2,'mode':'post_hoc_six_marker_single_file_pair_diagnostic'})
pd.DataFrame(out).to_csv(O/'zeb2-single-file-pair-diagnostic.tsv',sep='\t',index=False)
s={'source':'GSE74381','QC':qc,'discrepancy':'Cuffdiff summary table Pmp22 rises (15.2952 to33.7436); deposited control/KO transcript-file Pmp22 falls (12152.8 to470.812). Metadata assigns the same two filenames to both replicate GSM records, so they cannot be reconstructed as four replicates or assumed identical to group summary. Preserve conflicting encodings without choosing the one that agrees with the paper.','limits':'Six-marker panel only; Mpz control HIDATA. No independent-replicate uncertainty and no prospective credit. Both representations are the same source study, not two validations. Cross-assay calibration versus age/Cre effects remains unresolved.','diagnostic_results':out};(O/'zeb2-representation-audit.json').write_text(json.dumps(s,indent=2,allow_nan=False));print(T.to_string());print(pd.DataFrame(out).to_string(index=False))
