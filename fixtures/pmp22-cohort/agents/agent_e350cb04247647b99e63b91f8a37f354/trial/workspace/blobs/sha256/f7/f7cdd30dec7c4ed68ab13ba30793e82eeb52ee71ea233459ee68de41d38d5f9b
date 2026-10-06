import json, textwrap
from pathlib import Path
P=Path(__file__).resolve().parents[1]
d=json.loads((P/'sources/GSE139321-metadata.json').read_text())
seen=set()
def walk(x):
 if isinstance(x,dict):
  if 'fields' in x:
   f=x['fields'];i=f.get('Sample_geo_accession')
   if i and str(i) not in seen:
    seen.add(str(i));print(json.dumps({k:v for k,v in f.items() if k in ['Sample_geo_accession','Sample_title','Sample_source_name_ch1','Sample_characteristics_ch1','Sample_growth_protocol_ch1','Sample_treatment_protocol_ch1','Sample_data_processing','Sample_library_strategy','Sample_library_source','Sample_library_selection']},indent=2))
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(d)
seq=json.loads((P/'sources/primary/rn5-Pmp22-promoter-sequence.json').read_text())['dna'].upper()
for name,s in [('P1','GAGGAAGGGCGTACACCATTG'),('P2','CGAGTTTGTGCCTGAGGCTAC')]:
 positions=[i+49315000 for i in range(len(seq)) if seq.startswith(s,i)];print('PRIMER',name,s,positions)
d=json.loads((P/'sources/community/PMP22-final-review.json').read_text())
print('FORUM',type(d), list(d) if isinstance(d,dict) else len(d))
for r in d.get('items',[]): print(r.get('id'),r.get('title'),r.get('created'))
