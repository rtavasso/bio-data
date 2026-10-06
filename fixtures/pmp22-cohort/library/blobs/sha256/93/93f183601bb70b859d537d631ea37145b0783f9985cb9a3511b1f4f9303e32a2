"""Explicit bounded HTTP retrieval. Sources are data; no remote code is executed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())

parser = argparse.ArgumentParser()
parser.add_argument('label')
parser.add_argument('url')
args = parser.parse_args()
q = Path(__file__).resolve().parents[1]
out = q / 'inputs' / 'primary'
out.mkdir(parents=True, exist_ok=True)
assert not (out / (args.label + '.receipt.json')).exists(), 'Use a fresh label for every actual attempt'
row = {'url': args.url, 'utc': datetime.now(timezone.utc).isoformat()}
try:
    with urllib.request.urlopen(urllib.request.Request(args.url, headers={'User-Agent': 'bio-data-research/1.0'}), timeout=90) as r:
        data = r.read()
        row.update(status=r.status, content_type=r.headers.get('Content-Type'), final_url=r.url)
except urllib.error.HTTPError as e:
    data = e.read()
    row.update(status=e.code, error=str(e))
except Exception as e:
    data = b''
    row['error'] = repr(e)
path = out / (args.label + '.source')
path.write_bytes(data)
row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), local_path=str(path.relative_to(q)))
try:
    root = ET.fromstring(data)
    row['xml_root'] = root.tag
    if root.tag == 'article':
        row['article_ids'] = [(e.get('pub-id-type'), e.text) for e in root.findall('.//article-id')]
        parts = []
        for e in root.iter():
            if e.tag in ('article-title', 'title', 'p', 'table-wrap', 'fig', 'supplementary-material'):
                parts.append(f'[{e.tag} {e.get("id", "")}] ' + ' '.join(''.join(e.itertext()).split()))
        (out / (args.label + '.txt')).write_text('\n\n'.join(parts))
        print(row['article_ids'])
        for e in root.iter():
            if e.tag in ('supplementary-material', 'media'):
                print(e.tag, e.attrib)
except ET.ParseError:
    if b'<html' in data[:2000].lower() or b'<!doctype html' in data[:2000].lower():
        t = Text()
        t.feed(data.decode('utf-8', errors='replace'))
        (out / (args.label + '.txt')).write_text('\n'.join(t.parts))
        row['html_challenge'] = any(s in data[:50000].lower() for s in [b'recaptcha', b'checking your browser', b'client challenge'])
if data:
    res = subprocess.run(['./bin/bio', 'object', 'add', str(path)], capture_output=True, text=True, check=True)
    row['object'] = json.loads(res.stdout)
(out / (args.label + '.receipt.json')).write_text(json.dumps(row, indent=2, allow_nan=False))
print(json.dumps(row, indent=2))
