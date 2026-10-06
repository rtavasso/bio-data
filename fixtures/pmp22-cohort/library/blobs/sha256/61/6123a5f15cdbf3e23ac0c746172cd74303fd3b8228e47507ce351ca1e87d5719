from pathlib import Path
import json,re
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
d=json.loads((I/'PXD043917-files-r002.json').read_text());summary=[]
for f in d:
 row={k:f.get(k) for k in ['fileName','fileSizeBytes','fileCategory','publicFileLocations']};summary.append(row)
 print(f['fileName'],f['fileSizeBytes'],f['fileCategory']['value'])
(O/'PXD043917-file-summary.json').write_text(json.dumps(summary,indent=2))
project=json.loads((I/'PXD043917-project.json').read_text());print(json.dumps(project,indent=2))
lines=[]
for s in (I/'GSE241269-family.soft').open():
 if s.startswith('^SAMPLE') or s.startswith(('!Sample_title','!Sample_characteristics','!Sample_data_processing','!Sample_supplementary','!Sample_description','!Sample_source_name')):lines.append(s.rstrip())
(O/'GSE241269-sample-metadata.txt').write_text('\n'.join(lines));print('\n'.join(lines))
for p in ['NEDD-metadata-inventory-log.txt']:
 print((O/p).read_text()[-7000:])
