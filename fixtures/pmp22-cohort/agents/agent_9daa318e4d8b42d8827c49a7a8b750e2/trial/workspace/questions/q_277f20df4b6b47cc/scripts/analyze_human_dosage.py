import pathlib,json,gzip,io,csv
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
q=pathlib.Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs'
s=gzip.decompress((d/'GSE7423-matrix.txt.gz').read_bytes()).decode();md,table=s.split('!series_matrix_table_begin\n');table=table.split('!series_matrix_table_end')[0];f=pd.read_csv(io.StringIO(table),sep='\t',dtype={'ID_REF':str});cols=f.columns[1:].tolist();assert len(cols)==12
metadata={}
for row in csv.reader(io.StringIO(md),delimiter='\t'):
 if row and row[0].startswith('!Sample'):metadata.setdefault(row[0],[]).append(row[1:])
text=gzip.decompress((d/'GPL1708.annot.gz').read_bytes()).decode();annot=pd.read_csv(io.StringIO(text.split('!platform_table_begin\n')[1].split('!platform_table_end')[0]),sep='\t',dtype=str).rename(columns={'ID':'ID_REF'})
assert not annot.ID_REF.duplicated().any();f=f.merge(annot[['ID_REF','Gene symbol','Gene title','Platform_SPOTID','GenBank Accession']],on='ID_REF',how='left',validate='one_to_one')
# Exact mapping from series titles/characteristics, not number of arrays as donor count.
mapping={'BON':['GSM178536','GSM178752'],'MAR':['GSM178753','GSM178754'],'BAR':['GSM178756','GSM178757'],'JIM':['GSM178758','GSM178759'],'AAL':['GSM178760'],'ETT':['GSM178761','GSM178762'],'LEY':['GSM178763']}
for donor,cc in mapping.items():f[donor+'_mean_log10_ratio']=f[cc].mean(axis=1)
normal=f[[a+'_mean_log10_ratio' for a in ['AAL','ETT','LEY']]].mean(axis=1)
for donor in ['BAR','JIM','BON','MAR']:
 f[donor+'_minus_normal_mean_log10']=f[donor+'_mean_log10_ratio']-normal;f[donor+'_vs_normal_geometric_ratio']=10**f[donor+'_minus_normal_mean_log10']
f.to_csv(o/'human-dosage-all-probes.tsv',sep='\t',index=False,na_rep='NA')
p=f[f['Gene symbol'].isin(['PMP22','SOX10','EGR2','JUN','MPZ','MBP','G3BP1','CANX','RER1','UGGT1'])];p.to_csv(o/'human-dosage-regulator-probes.tsv',sep='\t',index=False,na_rep='NA')
qc=[]
for donor,cc in mapping.items():
 if len(cc)==2:
  v=f[cc].dropna();qc.append({'donor':donor,'array1':cc[0],'array2':cc[1],'Pearson_log10_ratio':v.corr().iloc[0,1],'median_array2_minus_array1_log10':float((v[cc[1]]-v[cc[0]]).median()),'median_absolute_difference':float((v[cc[1]]-v[cc[0]]).abs().median())})
pd.DataFrame(qc).to_csv(o/'human-dosage-technical-qc.tsv',sep='\t',index=False)
# Broader ranked changes retain probes; no significance or gene collapse.
valid=f['Gene symbol'].notna()&~f['Gene symbol'].str.contains('///',na=False)
f.loc[valid].assign(abs_difference=lambda x:x.BAR_minus_normal_mean_log10.abs()).sort_values('abs_difference',ascending=False).head(100).to_csv(o/'human-dosage-broad-extremes.tsv',sep='\t',index=False)
summary={'experiment':'GSE7423/GPL1708','endpoint':'Source VALUE explicitly log10(normalized Cy3 test/Cy5 pooled reference), not log2 or RNA counts. Zero log ratio means equal test/reference signals, not absent RNA.','source_value_evidence':'inputs/continuation/GSM178757-quick.soft #VALUE','probe_rows':len(f),'unique_probes':int(f.ID_REF.nunique()),'missing_numeric_cells':int(f[cols].isna().sum().sum()),'donor_mapping':mapping,'genotypes':{'BAR':'PMP22 duplication, ONE donor','JIM':'PMP22 Leu16Pro, ONE different donor; not second duplication replicate','BON':'CTDP1 IVS6+389C>T','MAR':'CTDP1 IVS6+389C>T','AAL':'normal','ETT':'normal','LEY':'normal'},'normal_donor_weighting':'Technical array log10 ratios averaged within donor; normal mean across three donors equally weighted. Fold ratio=10**difference, common reference cancels. No fresh normalization.','biological_scope':'Cultured human Schwann cells below passage 10, proliferative heregulin/forskolin/IBMX medium; duplication donor plantar-nerve origin differs from other biopsies. Not mature myelinating Schwann cells.','formal_inference':'No genotype-effect p-value: duplication and L16P each one donor, culture/tissue/donor confounding. Historical labels of two HMSN1A biological replicates must not pool unlike variants.','PMP22_probes':f.loc[f['Gene symbol']=='PMP22',['ID_REF','Platform_SPOTID','GenBank Accession',*cols,'BAR_vs_normal_geometric_ratio','JIM_vs_normal_geometric_ratio']].to_dict('records'),'probe_limitation':'Two annotated probes kept separate; annotation accession does not prove promoter-specific binding. Probe 33317 maps a cDNA clone; no P1/P2 assignment.'}
(o/'human-dosage-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(pd.DataFrame(qc))
