"""Register already-executed packaging outputs and verify exact catalog readback."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
root = w.parent
out = q / 'outputs'
receipts = out / 'registrations'
receipts.mkdir(exist_ok=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(args):
    p = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def obj(path):
    value = call(['object', 'add', str(path)])
    assert value['blob'] == sha(path)
    return value['blob']


producer = q / 'scripts/export_protein_evidence.py'
execution = out / 'export-execution-r001.json'
ex = json.loads(execution.read_text())
assert ex['complete'] and ex['exit_code'] == 0 and ex['code_sha256'] == sha(producer)
manifest = json.loads((out / 'share-manifest.json').read_text())
inputs = manifest['original_artifacts'] + [obj(execution), obj(out / 'source-receipts.redacted.json')]
old = w / 'questions/q_277f20df4b6b47cc'
for relative in ['inputs/continuation/PMC4227013.xml',
                 'outputs/protein-analysis-log.txt', 'outputs/protein-analysis-stderr.txt']:
    inputs.append(obj(old / relative))
for name in sys.argv[1:]:
    assert name in {'protein-evidence.zip', 'share-manifest.json', 'byte-verification.json'}
    path = out / name
    expected = next(v for v in ex['outputs'] if Path(v['path']).name == name)
    assert expected['written'] and sha(path) == expected['sha256']
    args = ['register', str(path), '--question', q.name, '--title',
            'PMP22 PMC8191293 co-IP selective inherited evidence: ' + name,
            '--summary', 'Selective source/derivation byte preservation only; no scientific rerun.',
            '--code', str(producer), '--output-role', name,
            '--parameters', json.dumps({'operation': 'selective archive export and byte verification',
                                       'scientific_rerun': False, 'producer_receipt_sha256': sha(execution)})]
    for value in inputs:
        args += ['--input', value]
    result = call(args)
    (receipts / (name + '.json')).write_text(json.dumps(result, indent=2, allow_nan=False))
    assert not result.get('conflicting_outputs') and not result.get('warning')
    shown = call(['artifact', 'show', result['artifact']])
    assert shown['output_blob'] == sha(path) == result['output_blob']
    assert any(v['question_id'] == q.name for v in shown['questions'])
    (receipts / (name + '.readback.json')).write_text(json.dumps(shown, indent=2, allow_nan=False))
    print(name, result['artifact'], 'readback verified')
