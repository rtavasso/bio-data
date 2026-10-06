"""Register verified outputs through documented CLI and verify exact catalog readback."""
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
REG = OUT / 'registration'
REG.mkdir(exist_ok=True)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cli(args):
    p = subprocess.run(['./bin/bio', *map(str, args)], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f'{args}: {p.returncode}\n{p.stdout}\n{p.stderr}')
    return json.loads(p.stdout)


manifest = json.loads((OUT / 'source-manifest.json').read_text())
receipt = OUT / 'execution-r002.json'
execution = json.loads(receipt.read_text())
assert execution['complete'] and execution['exit_code'] == 0 and execution['code_unchanged']
for item in execution['outputs']:
    assert item['written'] and sha(Path(item['path'])) == item['sha256']
assert sha(Q / 'scripts/build_audit.py') == execution['code_sha256']

# Preserve hashes/receipts for all actually used and intentionally excluded inputs.
objects_path = REG / 'input-objects.json'
if objects_path.exists():
    objects = json.loads(objects_path.read_text())
else:
    objects = []
    for item in manifest['inputs']:
        p = Q / item['path']
        assert sha(p) == item['sha256']
        result = cli(['object', 'add', p])
        assert result['blob'] == item['sha256']
        objects.append(result)
    objects_path.write_text(json.dumps(objects, indent=2))
refs = []
for p in [receipt, OUT / 'execution-r001.json', OUT / 'validation.json']:
    result = cli(['object', 'add', p, '--classification', 'reference'])
    assert result['blob'] == sha(p)
    refs.append(result['blob'])
(REG / 'reference-objects.json').write_text(json.dumps(refs, indent=2))
env = REG / 'environment.json'
env.write_text(json.dumps({'python': platform.python_version(), 'producer_invocation': execution['argv'],
                           'receipt_sha256': sha(receipt)}, indent=2))
products = [
    ('endpoint-audit.json', 'endpoint-audit', 'PMP22 sterol/endocrine source-located endpoint audit'),
    ('assay-eligibility.tsv', 'assay-eligibility', 'Age species compartment and biological-unit eligibility'),
    ('source-manifest.json', 'source-locators', 'Immutable sources actual HTTP receipts and inherited provenance'),
    ('bidirectionality-design.json', 'bidirectionality-design', 'Proposed discriminating PMP22 lipid endocrine tests'),
    ('validation.json', 'audit-validation', 'Source anchors hashes and serialization validation'),
]
if sys.argv[1] == 'first':
    products = products[:1]
for filename, role, title in products:
    path = OUT / filename
    regfile = REG / f'{role}.json'
    if not regfile.exists():
        args = ['register', path, '--question', 'q_d14c6e25fa864ab5', '--title', title,
                '--summary', 'Validated agent-curated evidence eligibility, not a new biological experiment.',
                '--code', Q / 'scripts/build_audit.py', '--output-role', role,
                '--parameters', json.dumps({'scope': 'source-and-assay-audit', 'producer_invocation': execution['argv']}),
                '--environment', env]
        for h in sorted({x['blob'] for x in objects}):
            args.extend(['--input', h])
        for h in refs:
            args.extend(['--reference', h])
        registration = cli(args)
        regfile.write_text(json.dumps(registration, indent=2))
    else:
        registration = json.loads(regfile.read_text())
    artifact = registration['artifact']
    exact = cli(['artifact', 'show', artifact])
    (REG / f'{role}-readback.json').write_text(json.dumps(exact, indent=2))
    assert exact['output_blob'] == sha(path)
    assert exact['manifest']['output_role'] == role
    assert sha(Path(exact['path'])) == sha(path)
    print(json.dumps({'artifact': artifact, 'file': filename, 'sha256': sha(path), 'readback_verified': True}))
