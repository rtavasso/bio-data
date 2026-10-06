from pathlib import Path
import re
from acquire_iteration import fetch
q=Path(__file__).resolve().parents[1]
t=(q/'inputs/iteration/GSE49598-samples-metadata.soft').read_text()
for b in t.split('^SAMPLE = ')[1:]:
 gsm=b.splitlines()[0];urls=re.findall(r'!Sample_supplementary_file.* = (.*)',b)
 assert len(urls)==1
 fetch(urls[0].strip().replace('ftp://','https://'),gsm+'-features.txt.gz')
