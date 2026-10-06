import pathlib,json,gzip,hashlib,numpy as np,pandas as pd
q=pathlib.Path(__file__).resolve().parents[1];o=q/'outputs';d=q/'inputs/continuation'
r=pd.read_csv(o/'rna-all-features.tsv',sep='\t');cols=['LentiAS-1','LentiAS-2','LentiGFP-1','LentiGFP-2'];x=r[cols];globin=r.description.fillna('').str.contains('hemoglobin|globin',case=False,regex=True)&~r.description.fillna('').str.contains('globin locus|globin regulator',case=False)
panel=['Gata1','Klf1','Alas2','Slc4a1','Bpgm','Epor','Tal1','Gypa','Sptb','Epb42','Fech','Tfrc','Lmo2','Fli1','Ptprc','Pecam1','Col1a1','Sox10','Mpz','Pmp22','Egr2','Jun','Mtor']
r.loc[globin|r['#Geneid'].isin(panel)].to_csv(o/'rna-globin-followup.tsv',sep='\t',index=False)
# Sensitivity only: recompute median-ratio normalization excluding globin features.
pos=(x>0).all(axis=1)&~globin;sf=x.loc[pos].div(np.exp(np.log(x.loc[pos]).mean(axis=1)),axis=0).median();n=x.div(sf,axis=1)
z={}
for g in ['Pmp22','Egr2','Jun','Mtor']:
 i=r.index[r['#Geneid']==g][0];z[g]={'original_ratio':float(r.loc[i,'AS_over_GFP']),'excluding_globin_normalization_ratio':float(n.loc[i,cols[:2]].mean()/n.loc[i,cols[2:]].mean())}
fresh=gzip.decompress((d/'GSE201623-counts-fresh.txt.gz').read_bytes());old=pathlib.Path(json.loads((q/'inputs/continued-rna-source.json').read_text())['path']).read_bytes()
summary={'fresh_download_exact_byte_match':fresh==old,'source_sha256':hashlib.sha256(fresh).hexdigest(),'globin_selector':'description contains hemoglobin|globin, excludes globin locus|globin regulator; discovered from all-gene ranking, not preselected test','selected_globin_symbols':r.loc[globin,'#Geneid'].tolist(),'globin_count_sum':x.loc[globin].sum().to_dict(),'globin_fraction_of_all_gene_counts':x.loc[globin].sum().div(x.sum()).to_dict(),'normalization_sensitivity':z,'finding':'Globin-rich pattern is present in deposited bytes. Normalization sensitivity excludes selected globin features, not biological removal of contamination.','limits':'Gene counts do not identify read origin, vector sequences, ambient RNA or cell composition. Paralogous globin genes may share mapping ambiguity. No automatic raw reprocessing. No causal contamination diagnosis.'}
(o/'rna-globin-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(r.loc[r['#Geneid'].isin(panel),['#Geneid',*cols,'AS_over_GFP']].to_string(index=False))
