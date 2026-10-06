"""Register verified selective-export outputs with their actual packaging producer."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
root = w.parent
out = q / 'outputs'
reg = out / 'registrations'
reg.mkdir(exist_ok=True)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def call(args):
    result = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def obj(p):
    result = call(['object', 'add', str(p)])
    assert result['blob'] == sha(p)
    return result['blob']


producer = q / 'scripts/export_sources.py'
receipt = out / 'export-execution-r001.json'
execution = json.loads(receipt.read_text())
assert execution['complete'] and execution['exit_code'] == 0
assert execution['code_sha256'] == sha(producer)
manifest = json.loads((out / 'source-locator-manifest.json').read_text())
inputs = [x['artifact'] for x in manifest['original_artifacts']]
inputs += ['asset_53dd40f9b97a2571a2fb2632ea636cab']
for item in manifest['files']:
    if item['origin'].startswith('questions/q_277f20df4b6b47cc/'):
        p = w / item['origin']
        assert sha(p) == item['sha256']
        inputs.append(obj(p))
for p in [receipt, out / 'source-receipts.redacted.json', *sorted((q / 'inputs').glob('artifact_*.stdout.json'))]:
    inputs.append(obj(p))
inputs = sorted(set(inputs))
(out / 'registration-inputs.json').write_text(json.dumps(inputs, indent=2))
for name in sys.argv[1:]:
    expected = next(x for x in execution['outputs'] if Path(x['path']).name == name)
    p = out / name
    assert expected['written'] and sha(p) == expected['sha256']
    args = ['register', str(p), '--question', q.name,
            '--title', 'PMP22 GSE118660 GSE90070 selective source handoff: ' + name,
            '--summary', 'Exact inherited evidence and metadata locators; packaging only, no scientific rerun.',
            '--code', str(producer), '--output-role', name,
            '--parameters', json.dumps({'operation': 'unchanged-byte export and source-metadata checks',
                                       'scientific_rerun': False, 'execution_receipt_sha256': sha(receipt)})]
    for value in inputs:
        args += ['--input', value]
    result = call(args)
    (reg / (name + '.json')).write_text(json.dumps(result, indent=2, allow_nan=False))
    assert not result.get('warning') and not result.get('conflicting_outputs')
    check = call(['artifact', 'show', result['artifact']])
    assert check['output_blob'] == result['output_blob'] == sha(p)
    (reg / (name + '.readback.json')).write_text(json.dumps(check, indent=2, allow_nan=False))
    print(name, result['artifact'], 'readback verified')
