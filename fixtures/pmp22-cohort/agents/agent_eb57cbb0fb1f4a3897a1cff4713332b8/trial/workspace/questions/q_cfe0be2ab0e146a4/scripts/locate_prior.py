"""Inspect exact inherited manifests and selected plaintext; do not execute code."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'inputs' / 'prior'
OUT.mkdir(parents=True, exist_ok=True)
LIB = os.environ['BIO_COMMUNITY'] + '/library'

def cli(*args):
    return json.loads(subprocess.run(['./bin/bio', *args], check=True, capture_output=True, text=True).stdout)

def obj(blob):
    assert re.fullmatch('[a-f0-9]{64}', blob), blob
    meta = cli('--workspace', LIB, 'object', 'show', blob)
    raw = Path(meta['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == blob
    return raw

for aid in ['artifact_78fc412f0d9a4d6abdb740b28057e070257909b9fbd9456aedd01bca09e706b9', 'artifact_abee146fb898851d7990ccc5bce8cd7853e6998cdf03f02523f02a63ec2a88ed', 'artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a', 'artifact_b11c4fbe0536a4c827c7ee65a1159591b70693787d55c2bdff98379724cddc43']:
    meta = cli('--workspace', LIB, 'artifact', 'show', aid)
    (OUT / f'{aid}.manifest.json').write_text(json.dumps(meta, indent=2))
    raw = obj(meta['output_blob'])
    dest = OUT / meta['manifest']['output']['name']
    dest.write_bytes(raw)
    print(aid, meta['manifest']['title'], 'OUTPUT', dest.name, 'bytes', len(raw))
    if raw.startswith(b'{'):
        doc = json.loads(raw)
        print('keys', list(doc))
        (OUT / (dest.name + '.pretty.json')).write_text(json.dumps(doc, indent=2))
        def walk(v, loc=''):
            if isinstance(v, dict):
                if any(re.search('8191293|4227013|protein|mechanism|REPORT', str(x), re.I) for x in v.values() if isinstance(x,str)):
                    print(loc, json.dumps(v)[:1700])
                for k,x in v.items():
                    if isinstance(x,(dict,list)):
                        walk(x, loc+'/'+k)
            elif isinstance(v,list):
                for i,x in enumerate(v):
                    walk(x, loc+'/'+str(i))
        walk(doc)
pkg = json.loads((ROOT / 'inputs/community/ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3.pretty.json').read_text())
selected = []
for item in pkg['files'] + pkg['input_objects']:
    if re.search('REPORT|protein|PXD043917|mechanism', item['path'], re.I):
        print('SELECT', item['path'], item['sha256'])
        raw = obj(item['sha256'])
        dest = OUT / Path(item['path']).name
        if dest.exists() and dest.read_bytes() != raw:
            dest = OUT / (item['sha256'][:8] + '-' + dest.name)
        dest.write_bytes(raw)
        selected.append({'original_path': item['path'], 'sha256': item['sha256'], 'local': str(dest.relative_to(ROOT))})
(OUT/'selection.json').write_text(json.dumps(selected, indent=2))
