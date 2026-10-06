"""Derive source-compatible human mappings; retain ambiguous source convention."""
import gzip
import hashlib
import json
from pathlib import Path
import re
from html.parser import HTMLParser
Q=Path(__file__).resolve().parents[1]
class Text(HTMLParser):
    def __init__(self): super().__init__();self.out=[];self.skip=0
    def handle_starttag(self,t,a):
        if t in ['script','style']: self.skip+=1
        if t in ['p','h1','h2','h3','h4','li']: self.out.append('\n')
    def handle_endtag(self,t):
        if t in ['script','style']: self.skip-=1
        if t in ['p','h1','h2','h3','h4','li']: self.out.append('\n')
    def handle_data(self,d):
        if not self.skip:self.out.append(d)
for p in (Q/'inputs/reused-cis').glob('*.html'):
    h=Text();h.feed(p.read_text())
    lines=[' '.join(x.split()) for x in ''.join(h.out).splitlines() if x.strip()]
    (Q/'inputs/text'/f'{p.name}.txt').write_text('\n'.join(lines)+'\n')
# Literal human hg18 reporter intervals. Endpoint convention explicitly not certified by source.
source_intervals=[('P2_reporter',15106498,15106933,'PMC3100536; peer-confirmed; source not in reused ZIP'),
                  ('intronic_short',15091959,15092201,'PMC5181599 Methods Luciferase assays'),
                  ('intronic_large',15090965,15092611,'PMC3100536; peer-confirmed; source not in reused ZIP'),
                  ('A_distal',15253855,15254150,'PMC3298281 Methods Transfection assays'),
                  ('B_distal',15250013,15250409,'PMC3298281 Methods Transfection assays'),
                  ('C_distal',15221688,15222096,'PMC3298281 Methods Transfection assays')]
blocks=[];header=None
with gzip.open(Q/'inputs/public/hg18ToHg38.over.chain.gz','rt') as f:
    for i,line in enumerate(f):
        s=line.split()
        if not s: header=None;continue
        if s[0]=='chain':
            header=s;tx=int(s[5]);qx=int(s[10]);continue
        assert header is not None
        size=int(s[0])
        if header[2]=='chr17':
            assert header[4]=='+'
            blocks.append({'t0':tx,'t1':tx+size,'q0':qx,'q1':qx+size,'qchr':header[7],
                           'qstrand':header[9],'qsize':int(header[8]),'chain':header[12],'line':i+1})
        if len(s)==3:tx+=size+int(s[1]);qx+=size+int(s[2])

def convert(start,end):
    matches=[]
    for b in blocks:
        if b['t0']<=start and end<=b['t1']:
            left=b['q0']+start-b['t0'];right=b['q0']+end-b['t0']
            if b['qstrand']=='-':left,right=b['qsize']-right,b['qsize']-left
            matches.append(dict(b,mapped_start0=left,mapped_end0=right))
    return matches
mapped=[]
for name,start,end,source in source_intervals:
    row={'name':name,'source_assembly':'hg18','source_chromosome':'chr17','source_start_literal':start,
         'source_end_literal':end,'source_convention':'unspecified; analyze both 0-half-open and 1-closed',
         'source':source,'hypothesis_zero_half_open':convert(start,end),
         'hypothesis_one_closed':convert(start-1,end)}
    # Only certify a unique, unsplit block mapping under BOTH source conventions.
    assert len(row['hypothesis_zero_half_open'])==len(row['hypothesis_one_closed'])==1
    a=row['hypothesis_zero_half_open'][0];b=row['hypothesis_one_closed'][0]
    assert a['chain']==b['chain'] and a['qchr']==b['qchr']=='chr17'
    row.update(assembly='GRCh38',chromosome='chr17',
               outer_start0=min(a['mapped_start0'],b['mapped_start0']),outer_end0=max(a['mapped_end0'],b['mapped_end0']),
               core_start0=max(a['mapped_start0'],b['mapped_start0']),core_end0=min(a['mapped_end0'],b['mapped_end0']),
               mapping_orientation=a['qstrand'],source_strand='not explicitly specified')
    mapped.append(row)
    print(name,row['core_start0'],row['core_end0'],a['chain'])
result={'chain_source':'inputs/public/hg18ToHg38.over.chain.gz','sha256':hashlib.sha256((Q/'inputs/public/hg18ToHg38.over.chain.gz').read_bytes()).hexdigest(),
        'operation':'direct exact single-chain-block interval mapping; not cross-species lift; no mapping of rat response',
        'rows':mapped}
with (Q/'outputs/human-regulatory-mapping.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
o=json.loads((Q/'outputs/inspection-v11.json').read_text())
for x in o['genes']:
    if x['tissue'] in ['Nerve_Tibial','Cells_Cultured_fibroblasts','Adipose_Subcutaneous','Ovary','Skin_Sun_Exposed_Lower_leg']:
        print('TARGET',json.dumps({k:v for k,v in x.items() if k in ['assay','tissue','gene_id','phenotype_id','variant_id','pval_nominal','qval','slope','slope_se','num_var','group_size','start','end','tss_distance']}))
print('GENCORD QC excerpt')
h=Text();h.feed((Q/'inputs/public/catalogue-gencord-qc.html').read_text())
s=' '.join(''.join(h.out).split())
for term in ['sex','covariate','ancestry','fibroblast','186','genotype']:
    m=re.search(term,s,re.IGNORECASE)
    if m:print(term,s[max(0,m.start()-150):m.end()+800])
