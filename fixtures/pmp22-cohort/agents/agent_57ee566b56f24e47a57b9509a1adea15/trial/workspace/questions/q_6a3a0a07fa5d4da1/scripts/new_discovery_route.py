"""Generate exact public source queries/locators; no outcome inspection."""
import json,os,re,urllib.parse
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
term='"sciatic nerve" AND (crush OR transection) AND "expression profiling by high throughput sequencing"[DataSet Type] AND gse[Entry Type]'
url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'gds','term':term,'retmode':'json','retmax':100})
(q/'inputs/geo-query-urls.json').write_text(json.dumps({'geo-injury-search.json':url},indent=2))
root=ET.parse(q/'inputs/public/PMC4668002.xml').getroot();text=' '.join(root.itertext())
print('IDENTIFIERS',sorted(set(re.findall(r'GSE\d+|SRP\d+|PRJNA\d+|SRR\d+|E-MTAB-\d+',text))))
for i,p in enumerate(root.iter('p')):
    s=' '.join(p.itertext())
    if i in range(11,16) or re.search(r'data avail|accession|deposited|S1 Table',s,re.I):print(i,s[:3000])
for e in root.iter('supplementary-material'):
    caption=' '.join(e.itertext())
    if 'Table' in caption or 'table' in caption:print('SUPPLEMENT',caption[:500],[(c.tag,c.attrib) for c in e])
