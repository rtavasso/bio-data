"""Compact metadata for additional discovery branches and verify actual publications."""
import gzip,json,os,re,subprocess
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
for pmc in ['PMC5608958','PMC7195462','PMC8799715','PMC7735761','PMC3669361']:
    root=ET.parse(q/f'inputs/public/{pmc}.xml').getroot();text=' '.join(root.itertext())
    print(pmc,'ACCESSIONS',sorted(set(re.findall(r'GSE\d+|PRJNA\d+|E-MTAB-\d+|E-MEXP-\d+',text))))
    if pmc=='PMC7735761':
        for i,p in enumerate(root.iter('p')):
            s=' '.join(p.itertext())
            if re.search(r'bulk|GSE\d+|RNA.seq|biological replic',s,re.I): print(i,s[:1900])
    if pmc=='PMC7195462':
        for p in root.iter('supplementary-material'): print('SUPP',p.attrib,[(c.tag,c.attrib) for c in p])
with gzip.open(q/'inputs/public/GSE163132_series_matrix.txt.gz','rt') as f:
    for line in f:
        if line.startswith('!Sample_title') or line.startswith('!Sample_geo_accession'):print(line.strip())
        if line.startswith('!series_matrix_table_begin'):break
for name,body in [('screen-post-publication','screen-and-lock-post')]:
    x=json.loads((q/f'outputs/{name}.json').read_text())
    y=json.loads(subprocess.run(['./bin/bio','community','show',x['id']],capture_output=True,text=True,check=True).stdout)
    assert y['content']['body']==(q/f'outputs/{body}.md').read_text();print('EXACT_POST_READBACK_OK',y['id'])
for name in ['ask-rbp','ask-promoter']:
    x=json.loads((q/f'outputs/{name}.json').read_text());print(name,x)
