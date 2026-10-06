"""Compact inspection of archive layout, gene-level rows and site metadata strings."""
import json
from pathlib import Path
import re
import tarfile
from html import unescape
Q=Path(__file__).resolve().parents[1]
o=json.loads((Q/'outputs/inspection-v11.json').read_text())
for k,v in o['archive_inventory'].items(): print(k,v[:4])
for x in o['genes']:
    print(x['assay'],x['tissue'],x['gene_id'],x['qval'],x['variant_id'],x.get('group_size',''))
for x in o['covariates']:
    if any(t in x['member'] for t in ['Nerve_Tibial','Cells_Cultured','Skin_']): print(x)
with tarfile.open(Q/'inputs/public/v11-eqtl-susie.tar','r:') as tar:
    for m in tar.getmembers():
        if m.isfile() and 'fibro' in m.name:
            print('FIBRO SUSIE',m.name,m.size,tar.extractfile(m).read(600))
text=(Q/'inputs/public/gtex-app.js').read_text()
for term in ['analysisMethods','analysis_methods','documentation','GENCODE 47','staticTextAnalysis','min_ma','minor allele','PEER','v11']:
    matches=list(re.finditer(re.escape(term),text))
    print('APP',term,len(matches))
    for m in matches[:6]: print(unescape(text[max(0,m.start()-180):m.end()+350]))
search=json.loads((Q/'inputs/public/search-gtex-v10.json').read_text())
print('V10 LITERATURE total',search.get('hitCount'))
for x in search.get('resultList',{}).get('result',[]):
    if 'GTEx' in x['title'] or 'tissue' in x['title'].lower():
        print(x['id'],x.get('pmcid'),x['title'])
