"""Analyze source-reported selected TMT co-IP effects; never impute unlisted proteins."""
import pathlib,json,itertools
import openpyxl,pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
q=pathlib.Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs';p=d/'PMC8191293-mmc2.xlsx';wb=openpyxl.load_workbook(p,read_only=True,data_only=False)
rows=[]
for sheet in wb:
 for i,cells in enumerate(sheet.iter_rows(),1):
  if i==1:assert [c.value for c in cells]==['Accession','Description','Gene','Q-value','Avg Log2 transformation'];continue
  assert not any(c.data_type=='f' for c in cells), 'No formula evaluation'
  a,desc,g,qq,lfc=[c.value for c in cells]
  if a is None:continue
  assert isinstance(qq,(float,int)) and isinstance(lfc,(float,int))
  rows.append(dict(variant=sheet.title,source_sheet=sheet.title,source_row=i,accession=a,description=desc,gene=g,source_Storey_Q=qq,source_mean_log2_over_mock=lfc,fold_over_mock=2**lfc))
f=pd.DataFrame(rows);assert not f.duplicated(['variant','accession']).any();assert (f.source_Storey_Q<.1).all() and (f.source_mean_log2_over_mock>.2).all();f.to_csv(o/'protein-selected-interactors.tsv',sep='\t',index=False)
pivot=f.pivot(index='accession',columns='variant',values='source_mean_log2_over_mock');gene=f.drop_duplicates('accession').set_index('accession')['gene'];pivot.insert(0,'gene',gene);pivot['L16P_minus_WT_log2_selected']=pivot.L16P-pivot.WT;pivot['N41Q_minus_WT_log2_selected']=pivot.N41Q-pivot.WT;pivot['L16P_over_WT_enrichment_ratio']=2**pivot['L16P_minus_WT_log2_selected'];pivot['N41Q_over_WT_enrichment_ratio']=2**pivot['N41Q_minus_WT_log2_selected'];pivot.to_csv(o/'protein-interactor-comparisons.tsv',sep='\t',na_rep='NOT_LISTED')
sets={v:set(f.loc[f.variant==v,'accession']) for v in ['WT','N41Q','L16P']};union=set.union(*sets.values());inter=set.intersection(*sets.values());membership=[]
for k in union:membership.append({'accession':k,'gene':gene[k],'WT_listed':k in sets['WT'],'N41Q_listed':k in sets['N41Q'],'L16P_listed':k in sets['L16P']})
pd.DataFrame(membership).sort_values('accession').to_csv(o/'protein-list-membership.tsv',sep='\t',index=False)
# Broad data-driven follow-up: strongest contrasts among proteins actually listed in BOTH conditions.
shared=pivot.dropna(subset=['WT','L16P']).sort_values('L16P_minus_WT_log2_selected',ascending=False);shared.to_csv(o/'protein-shared-ranked.tsv',sep='\t',na_rep='NOT_LISTED')
fig,ax=plt.subplots(1,2,figsize=(12,5));ax[0].bar(list(sets),[len(s) for s in sets.values()]);ax[0].set(ylabel='Proteins in selected list',title='Selection counts (not interaction specificity)')
top=shared.head(18).iloc[::-1];ax[1].barh(top.gene,top.L16P_minus_WT_log2_selected);ax[1].set(xlabel='Source mean log2 enrichment: L16P − WT',title='Largest shared-list differences (descriptive)');fig.tight_layout();fig.savefig(o/'protein-interactor-summary.png',dpi=170);plt.close(fig)
raw=json.loads((d/'PXD023091-files.json').read_text());files=[{'file':a['fileName'],'bytes':a['fileSizeBytes'],'category':a['fileCategory']['value']} for a in raw]
summary={'source':'PMC8191293 Table S1 (mmc2.xlsx), PXD023091','endpoint':'TMT co-immunoprecipitated protein enrichment over mock untagged PMP22, not cellular abundance, surface trafficking, direct binding or functional mediation.','material':'Myc-tagged human PMP22 WT/N41Q/L16P constructs in HEK293 cells. Six biological co-IP replicates per construct across four 6-plex TMT batches reported in Methods. Supplement lacks replicate-level intensities/channel map.','selection':'Storey Q<0.1 and mean log2 enrichment over mock >0.2; workbook contains selected hits only. Missing entry = not listed, not measured-zero/noninteraction.','counts':{v:len(s) for v,s in sets.items()},'union':len(union),'all_three':len(inter),'shared_pairs':{a+'_'+b:len(sets[a]&sets[b]) for a,b in itertools.combinations(sets,2)},'formula_cells':0,'fresh_tests':'None. Source Q values retained, not recalculated. Difference of source mean log2 enrichments is descriptive and lacks SE/covariance.','batch_warning':'Primary Results sec1.4 explicitly attributes differing hit numbers partly to batch-to-batch MS power. Counts cannot establish broader true binding of N41Q.','candidate_contrasts':shared[['gene','WT','L16P','L16P_minus_WT_log2_selected','L16P_over_WT_enrichment_ratio']].head(15).reset_index().to_dict('records'),'PRIDE_inventory':files,'blocker':'All four deposited SEARCH .msf files exceed 1.18 GB, above 512 MiB/file limit. RAW spectra would require unauthorized raw processing. No small processed per-replicate/channel matrix in returned inventory. Selected XLSX used as lawful alternative.','functional_followup':'Source Figure 6 KO shows LMAN1 interaction does not imply trafficking requirement; UGGT1 not detected in screen yet affects trafficking. Surface transport not equal correctly myelinating function.'}
(o/'protein-analysis-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in summary.items() if k not in ['PRIDE_inventory']},indent=2))
