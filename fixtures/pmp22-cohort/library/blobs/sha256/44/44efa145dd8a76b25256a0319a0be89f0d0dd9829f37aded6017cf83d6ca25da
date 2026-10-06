"""Save exact metadata outputs and construct sample map before native-count acquisition."""
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree as ET

q = Path(__file__).resolve().parents[1]
o = q / 'inputs' / 'geo'
o.mkdir(parents=True, exist_ok=True)
log = Path('.hermes/cache/terminal-output/out-1791225524-61170-5480.log')
records = [json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
assert len(records) == 3
for item in records:
    subject = item['subject']
    (o / f'{subject}.json').write_text(json.dumps(item, indent=2))
    contexts = item['profiles'][0]['facts'].get('related_source_context', [])
    samples = []
    for x in contexts:
        if x.get('kind') == 'sample':
            f = x['body']['fields']
            samples.append({k: v for k, v in f.items() if k in ['Sample_geo_accession', 'Sample_title', 'Sample_description', 'Sample_characteristics_ch1', 'Sample_organism_ch1', 'Sample_treatment_protocol_ch1', 'Sample_growth_protocol_ch1', 'Sample_extract_protocol_ch1', 'Sample_data_processing', 'Sample_library_strategy', 'Sample_library_source', 'Sample_supplementary_file_1']})
    if subject.startswith('bundle'):
        (o / f'{subject}-samples.json').write_text(json.dumps(samples, indent=2))
        print(subject, len(samples), 'SAMPLES')
        for s in samples:
            print(s['Sample_geo_accession'], s['Sample_title'], s.get('Sample_library_strategy'))
            if '118660' in json.dumps(item.get('source', {})):
                print(s.get('Sample_treatment_protocol_ch1'))
# Paginated local listing, not new network discovery.
items = []
for offset in (0, 20):
    r = subprocess.run(['./bin/bio', 'data', 'list', '--scope', 'bundle_34c53097b66a18c0797661f1', '--offset', str(offset)], capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    (o / f'listing-{offset}.json').write_text(json.dumps(data, indent=2))
    items.extend(data['items'])
assert len(items) == data['total'] == 33
selected = [i for i in items if '_siControl_' in i['name'] or '_siIGF2BP3_' in i['name']]
assert len(selected) == 16
(o / 'selected-files.json').write_text(json.dumps(selected, indent=2))
print('SELECTED', len(selected))
root = ET.fromstring((q / 'inputs/primary/PMC2728407.xml').read_bytes())
for e in root.iter():
    if e.tag in ['supplementary-material', 'media', 'graphic']:
        print(e.tag, e.attrib)
