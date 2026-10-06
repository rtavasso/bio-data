"""Extract target rows from complete native public TSVs; verify CRC, hashes and tabix agreement."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs/independent-r002';OUT.mkdir(exist_ok=False)
manifest=[]
for filename,label in [('QTD000100.complete.all.tsv.gz','GENCORD'),('QTD000538.cc.tsv.gz','TwinsUK')]:
    p=Q/'inputs/public'/filename
    rec=json.loads(Path(str(p)+'.receipt.json').read_text())
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(2**22):h.update(b)
    assert h.hexdigest()==rec['sha256'] and p.stat().st_size==rec['bytes'] and rec['transport_complete']
    matches=[];loc=[]
    target=OUT/f'{label}-PMP22-native.tsv'
    with gzip.open(p,'rb') as f,target.open('xb') as out:
        header=f.readline();cols=header.decode().rstrip('\r\n').split('\t');out.write(header)
        n=1
        for n,line in enumerate(f,2):
            if b'ENSG00000109099' in line or (label=='TwinsUK' and b'clu_31787_-' in line):
                vals=line.decode().rstrip('\r\n').split('\t')
                assert len(vals)==len(cols)
                r=dict(zip(cols,vals))
                if label=='GENCORD' and r['molecular_trait_id']!='ENSG00000109099':continue
                out.write(line);matches.append(r);loc.append(n)
    if label=='GENCORD':
        tab=json.loads((Q/'inputs/ranges/QTD000100-15314994-all/result.json').read_text())
        t=[x for x in tab['records'] if x['molecular_trait_id']=='ENSG00000109099']
        assert len(t)==1
        m=[x for x in matches if x['variant']=='chr17_15314994_A_G'];assert len(m)==1
        assert all(t[0][k]==m[0][k] for k in cols)
        print('PRIMARY',m[0])
    counts={'source':str(p.relative_to(Q)),'source_sha256':h.hexdigest(),'all_rows':n-1,'target_rows':len(matches),
            'unique_variants':len({x['variant'] for x in matches}),
            'unique_traits':sorted({x['molecular_trait_id'] for x in matches}),
            'selected_path':str(target.relative_to(Q)),'source_line_numbers':loc,
            'crc_full_stream_passed':True,'all_tested':label=='GENCORD',
            'selection_note':'Complete all-tested native table' if label=='GENCORD' else 'Complete .cc export; not assumed to be all tested'}
    manifest.append(counts)
    print(label,{k:v for k,v in counts.items() if k!='source_line_numbers'})
with (OUT/'extraction-validation.json').open('x') as f:json.dump(manifest,f,indent=2,allow_nan=False)
p=Q/'inputs/public/PMC8423625.xml'
r=ET.fromstring(p.read_bytes())
texts=[]
for i,e in enumerate(r.iter()):
    if e.tag in ['p','title','article-title','caption']:
        s=' '.join(' '.join(e.itertext()).split());texts.append(f'[element={i}] {s}')
        if any(x in s.lower() for x in ['compressed','clump','related','one million','minor allele','covariate']):print('METHOD',s[:2200])
(Q/'inputs/text/PMC8423625.xml.txt').write_text('\n\n'.join(texts)+'\n')
