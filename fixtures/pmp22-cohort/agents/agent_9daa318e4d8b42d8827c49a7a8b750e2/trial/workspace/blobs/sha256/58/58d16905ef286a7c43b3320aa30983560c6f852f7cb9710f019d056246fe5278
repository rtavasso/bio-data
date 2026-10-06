from pathlib import Path
import json,gzip,re,io,hashlib
import pandas as pd,numpy as np
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/iteration';O=Q/'outputs/iteration';W=Q.parents[1]
inv=json.loads((O/'validation-input-objects.json').read_text())
def source(n):
 h=inv[n]['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;return p
assert '#VALUE = Normalized signal intensity (log2)' in source('GSM1202400.soft').read_text()
t=gzip.open(source('GSE49598_matrix.txt.gz'),'rt').read();table=t.split('!series_matrix_table_begin\n')[1].split('!series_matrix_table_end')[0];raw=pd.read_csv(io.StringIO(table),sep='\t',index_col=0)
t=source('GPL10787.soft').read_text().split('!platform_table_begin\n')[1].split('!platform_table_end')[0];ann=pd.read_csv(io.StringIO(t),sep='\t',dtype=str).set_index('ID');assert ann.index.is_unique and raw.index.is_unique
s=[]
for b in source('GSE49598-samples-metadata.soft').read_text().split('^SAMPLE = ')[1:]:
 s.append({'gsm':b.splitlines()[0],'title':re.search(r'!Sample_title = (.*)',b)[1].strip(),'genotype':re.search(r'genotype: (.*)',b)[1].strip(),'treatment':re.search(r'treatment: (.*)',b)[1].strip()})
s=pd.DataFrame(s).set_index('gsm');s.to_csv(O/'genetic-samples.tsv',sep='\t');assert set(raw.columns)==set(s.index)
# log2 values may be negative. They are not failed zeros or negative abundance.
eligible=np.isfinite(raw).all(axis=1);ann=ann.reindex(raw.index);pmp=ann.index[ann.GENE_SYMBOL=='Pmp22'];assert len(pmp)==2
raw.loc[pmp].to_csv(O/'genetic-pmp22-source.tsv',sep='\t');ann.loc[pmp].to_csv(O/'genetic-probe-mapping.tsv',sep='\t')
results=[]
for genotype in s.genotype.unique():
 a=s[(s.genotype==genotype)&(s.treatment!='Untreated')].index;b=s[(s.genotype==genotype)&(s.treatment=='Untreated')].index
 x,y=raw[a],raw[b];effect=x.mean(axis=1)-y.mean(axis=1)
 pair=x.to_numpy()[:,:,None]-y.to_numpy()[:,None,:]
 results.append(pd.DataFrame({'probe':raw.index,'gene':ann.GENE_SYMBOL.to_numpy(),'genotype':genotype,'eligible':eligible.to_numpy(),'n_treated':len(a),'n_control':len(b),'log2_effect':effect.to_numpy(),'pairwise_min':np.nanmin(pair,axis=(1,2)),'pairwise_max':np.nanmax(pair,axis=(1,2))}))
r=pd.concat(results);base=r[r.genotype=='Wild Type'].set_index('probe').log2_effect;r['interaction_vs_WT']=r.log2_effect.to_numpy()-r.probe.map(base).to_numpy();r.to_csv(O/'genetic-all-effects.tsv',sep='\t',index=False)
r[r.gene=='Pmp22'].to_csv(O/'genetic-pmp22-effects.tsv',sep='\t',index=False)
x=r[r.gene=='Pmp22'];med=x.groupby('genotype')[['log2_effect','interaction_vs_WT']].median();wt=med.loc['Wild Type','log2_effect'];ko=med.loc['PERKKO','interaction_vs_WT'];aa=med.loc['eIF2a A/A','interaction_vs_WT']
passed=bool(wt<=-.5 and ko>=.5 and aa>=.5 and (x[x.genotype=='Wild Type'].log2_effect<0).all())
# Orthogonal footprint endpoint, NOT matched RNA or biological replication.
c=pd.read_csv(source('GSE118660_MEF-counts.txt.gz'),compression='gzip',sep='\t',index_col=0);tpm=pd.read_csv(source('GSE118660_MEF-tpm.txt.gz'),compression='gzip',sep='\t',index_col=0)
assert c.index.equals(tpm.index) and c.columns.equals(tpm.columns) and c.index.is_unique
assert np.isfinite(c).all().all() and (c>=0).all().all();good=(c>=10).all(axis=1)&(tpm>4).all(axis=1)
pos=(c>0).all(axis=1);gm=np.exp(np.log(c.loc[pos]).mean(axis=1));sf=c.loc[pos].div(gm,axis=0).median(axis=0);sf/=np.exp(np.log(sf).mean());out=[]
for method,n in [('TPM',tpm),('median_ratio',c/sf),('CPM',c/c.sum()*1e6)]:
 for hour in [1,2,5,8]:
  wt=np.log2(n[f'PERK_WT_Tg{hour}hr'].where(n[f'PERK_WT_Tg{hour}hr']>0)/n.PERK_WT_Control.where(n.PERK_WT_Control>0));ko=np.log2(n[f'PERK_KO_Tg{hour}hr'].where(n[f'PERK_KO_Tg{hour}hr']>0)/n.PERK_KO_Control.where(n.PERK_KO_Control>0))
  z=pd.DataFrame({'gene':c.index,'method':method,'hour':hour,'eligible':good.to_numpy(),'WT_log2_effect':wt.to_numpy(),'KO_log2_effect':ko.to_numpy(),'KO_minus_WT':(ko-wt).to_numpy()});z['WT_percentile']=z.WT_log2_effect.where(good.to_numpy()).rank(pct=True);out.append(z)
z=pd.concat(out);z.to_csv(O/'footprint-all-effects.tsv',sep='\t',index=False);z[z.gene=='Pmp22'].to_csv(O/'footprint-pmp22-effects.tsv',sep='\t',index=False)
c.loc[['Pmp22']].to_csv(O/'footprint-pmp22-counts.tsv',sep='\t');tpm.loc[['Pmp22']].to_csv(O/'footprint-pmp22-TPM.tsv',sep='\t')
summary={'primary_pass':passed,'primary_status':'supported_in_scope' if passed else 'inconclusive_threshold_failure','primary_medians':med.reset_index().to_dict(orient='records'),'array_rows':len(raw),'array_finite_all_samples':int(eligible.sum()),'Pmp22_eligible':bool(eligible.loc[pmp].all()),'Pmp22_probe_count':len(pmp),'array_semantics':'Deposited normalized log2 intensity, no relog. Source excludes nonuniform flagged features; per-cell flags and precise normalization/centering not in series matrix. Negative log2 values retained.','replication':'WT4 and mutants2 labelled replicates/group, no donor independence assumed; no inferential p-values. Probe variants are not independent experiments.','footprint_rows':len(c),'footprint_eligible':int(good.sum()),'footprint_Pmp22_eligible':bool(good.loc['Pmp22']),'footprint_min_Pmp22_count':float(c.loc['Pmp22'].min()),'footprint_min_Pmp22_TPM':float(tpm.loc['Pmp22'].min()),'footprint_limits':'One library/genotype/time. Source mentions TPM flooring4 but deposits values below4; eligibility excludes floor-sensitive values. Footprints conflate RNA abundance, ribosome occupancy and elongation. No matched RNA, no absolute synthesis, no independent validation of translation efficiency.'}
(O/'genetic-validation-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(x.to_string(index=False));print(z[z.gene=='Pmp22'].to_string(index=False))
