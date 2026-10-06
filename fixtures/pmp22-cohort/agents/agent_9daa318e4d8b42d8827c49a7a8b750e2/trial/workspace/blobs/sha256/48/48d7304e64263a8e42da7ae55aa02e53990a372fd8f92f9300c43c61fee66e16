import pathlib,json,re,csv
from defusedxml import ElementTree as E
q=pathlib.Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs';root=E.parse(d/'PMC3866477.xml').getroot();t=next(e for e in root.iter('table-wrap') if e.get('id')=='T1');rows=[]
for tr in t.iter('tr'):
 cells=[''.join(c.itertext()).strip() for c in tr if c.tag in ['td','th']]
 if len(cells)==2 and cells[0] in ['SiCtrl','SiG3BP1','SiG3BP2','SiG3BP1/2']:
  nums=re.findall(r'\d+(?:\.\d+)?',cells[1]);mean,sem=map(float,nums[:2]);rows.append({'condition':cells[0],'source_cell':cells[1],'half_life_hours':mean,'SEM_hours':sem,'n_source_independent_experiments':3,'ratio_to_control_mean':mean/4.4})
assert len(rows)==4
with (o/'g3bp-half-life.tsv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
s=(o/'source-text/g3bp1-table.txt').read_text();matches=re.findall(r'PMP22\s+(-?[\d,]+)\s+([\d,]+)',s);assert len(matches)==3
contrasts=['control vs siG3BP1+siG3BP2','control vs siG3BP1','siG3BP2 vs siG3BP1+siG3BP2'];c=[]
for (lfc,p),contrast in zip(matches,contrasts):c.append({'comparison_source':contrast,'PMP22_source_logFC':float(lfc.replace(',','.')),'source_adjusted_p':float(p.replace(',','.')),'direction':'PMP22 higher in G3BP1-depleted condition; source control-minus-KD contrast','locator':'Supplementary Table1 page1 columns 2 and 1, then page2 column1; parsed text order audited against layout'})
result={'half_lives':rows,'selected_microarray_PMP22':c,'context':'MCF-7 human breast cancer cells, three separate microarray experiments reported; no transfer to Schwann cells.','source_table_semantics':'Supplement lists selected differentially expressed genes, not complete universe. No PMP22 entry under siG3BP2-only is absence from a selected list, not zero response.','finding':'G3BP1-depleted PMP22 RNA increases while half-life mean 4.2h vs control4.4h is not prolonged. Source reports no significant stability difference. Neither fresh significance nor equivalence tested without replicate values.','source_validation':'Results report PMP22 validated with three independent siG3BP1 oligonucleotides; other tested microarray candidates failed consistent qPCR across siRNAs. Broad screen alone did not establish all targets.','limits':'Cannot estimate synthesis, degradation rates or mediation from unmatched summary assays. Direct G3BP1-PMP22 binding not established by RNA-binding-protein classification.'}
(o/'g3bp-endpoint-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(result,indent=2))
