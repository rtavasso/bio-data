"""Inspect small archive members and download-link metadata, without executing inherited material."""
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'inputs/public'

class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {'href', 'src', 'data'} and value and any(x in value.lower() for x in ['download', 'bitstream', '.xls', '.pdf', '/sd/']):
                print(tag, key, value)
for name in ['JCI201297-supplement.pdf', 'JCI201297-data.xlsx']:
    print(name, 'HTML wrappers, not their filename-assumed types')
    Links().feed((P/name).read_text())
raw = (P/'CAM40408.html').read_text()
match = re.search(r'<script id="dspace-angular-state" type="application/json">(.*?)</script>', raw, re.S)
state = json.loads(match.group(1))
(P/'CAM40408-state.json').write_text(json.dumps(state, indent=2))
files = []
def walk(node):
    if isinstance(node, dict):
        if 'sizeBytes' in node:
            files.append({key: node.get(key) for key in ['_name', 'sizeBytes', '_links', 'metadata']})
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for value in node:
            walk(value)
walk(state)
(P/'CAM40408-files.json').write_text(json.dumps(files, indent=2))
for entry in files:
    print('CAM', entry['_name'], entry['sizeBytes'], entry['_links'].get('content'))
with zipfile.ZipFile(P/'PMC7771966-supplements.zip') as z:
    inventory = [{'name': item.filename, 'bytes': item.file_size} for item in z.infolist()]
    (P/'PMC7771966-supplements.inventory.json').write_text(json.dumps(inventory, indent=2))
    print('UGGT archive', json.dumps(inventory))
