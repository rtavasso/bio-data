"""Structural inspection of acquired RNA and processed mzIdentML; no raw reprocessing."""
from pathlib import Path
import json,gzip,csv,collections
from defusedxml.ElementTree import iterparse
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream';W=Q.parents[1]
receipts=json.loads((I/'rna-fetch-receipts.json').read_text());reports=[]
for a in receipts:
 h=a['receipt']['blob'];p=W/'blobs/sha256'/h[:2]/h
 with gzip.open(p,'rt') as f:
  r=csv.reader(f,delimiter='\t');header=next(r);first=[next(r) for _ in range(2)];n=2+sum(1 for _ in r)
 rep=dict(name=a['name'],blob=h,header=header,first_rows=first,rows=n);reports.append(rep);print(rep)
(O/'rna-structure.json').write_text(json.dumps(reports,indent=2))
# Process all result XML elements, no spectrum arithmetic or software execution.
p=I/'peptides_1_1_0.mzid.gz';tags=collections.Counter();params=collections.Counter();software=[];db=[];spectra=[];target_db=[];quant=[]
with gzip.open(p,'rb') as f:
 for ev,e in iterparse(f,events=['end']):
  tag=e.tag.rsplit('}',1)[-1];tags[tag]+=1
  if tag in ['cvParam','userParam']:
   params[(e.attrib.get('accession',''),e.attrib.get('name',''))]+=1
   if any(s in e.attrib.get('name','').lower() for s in ['abundance','intensity','area','quantitation','quantity']):
    if len(quant)<30:quant.append(e.attrib)
  if tag in ['DBSequence','SearchDatabase','SpectraData','AnalysisSoftware']:
   text=' '.join(e.itertext());record=dict(tag=tag,attributes=e.attrib,text=text[:1000],children=[{'tag':x.tag.rsplit('}',1)[-1],'attributes':x.attrib,'text':x.text} for x in e.iter() if x is not e and x.tag.rsplit('}',1)[-1] in ['cvParam','userParam']])
   if tag=='DBSequence':
    if 'PMP22' in str(record).upper() or 'MYELIN PROTEIN 22' in str(record).upper():target_db.append(record)
   elif tag=='SearchDatabase':db.append(record)
   elif tag=='SpectraData':spectra.append(record)
   else:software.append(record)
  # Keep child params until parent identification metadata is extracted; clear large items afterwards.
  if tag in ['DBSequence','Peptide','PeptideEvidence','SpectrumIdentificationResult','ProteinAmbiguityGroup','SpectraData','SearchDatabase','AnalysisSoftware']:e.clear()
result=dict(tags=dict(tags),params=[dict(accession=k[0],name=k[1],occurrences=v) for k,v in params.items()],software=software,search_databases=db,spectra=spectra,target_db=target_db,quantitative_parameter_examples=quant)
(O/'proteome-mzid-inspection.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({k:result[k] for k in ['software','search_databases','target_db','quantitative_parameter_examples']},indent=2));print('tags',dict(tags))
