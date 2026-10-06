"""Register core export separately from the optional native supplement."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
root = w.parent
old = w / 'questions/q_277f20df4b6b47cc'
out = q / 'outputs'
reg = out / 'registrations'
reg.mkdir(exist_ok=True)
producer = q / 'scripts/export_sources.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(args):
    p = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def obj(path):
    r = call(['object', 'add', str(path)])
    assert r['blob'] == sha(path)
    return r['blob']


for name in sys.argv[1:]:
    supplement = name == 'ADVS-13-e20323-s002.docx'
    receipt = out / ('supplement-export-execution-r001.json' if supplement else 'export-execution-r001.json')
    execution = json.loads(receipt.read_text())
    assert execution['complete'] and execution['exit_code'] == 0 and execution['code_sha256'] == sha(producer)
    expected = next(x for x in execution['outputs'] if Path(x['path']).name == name)
    assert expected['written'] and expected['sha256'] == sha(out / name)
    paths = [receipt, out / 'archive-inspection.json', out / 'inspection-execution-r001.json']
    if supplement:
        paths.append(old / 'inputs/upstream/ADVS-13-e20323-s002.docx')
        inputs = []
    else:
        manifest = json.loads((out / 'source-locator-manifest.json').read_text())
        inputs = [x['artifact'] for x in manifest['original_artifacts']]
        paths += [old / 'inputs/continuation/PMC6607759.html',
                  old / 'outputs/upstream/FDFT1-data-inventory.json',
                  old / 'outputs/upstream/FDFT1-archive-inventory.json',
                  old / 'scripts/upstream_inventory.py', old / 'outputs/continuation-registration.json',
                  out / 'source-receipts.redacted.json', out / 'pmc6623163-candidate-inspection.json',
                  out / 'candidate-article-identities.txt', q / 'inputs/original-lipid-artifact.json',
                  q / 'inputs/original-lipid-table-artifact.json']
    inputs = sorted(set(inputs + [obj(p) for p in paths]))
    args = ['register', str(out / name), '--question', q.name,
            '--title', 'PMP22 ABCA1 LXR FDFT1 selective source handoff: ' + name,
            '--summary', 'Unchanged inherited evidence; no scientific rerun; primary-source availability explicit.',
            '--code', str(producer), '--code', str(q / 'scripts/inspect_archives.py'), '--output-role', name,
            '--parameters', json.dumps({'operation': 'native-docx-copy' if supplement else 'selective-core-export',
                                       'scientific_rerun': False, 'execution_receipt_sha256': sha(receipt),
                                       'large_archives_excluded': True})]
    for value in inputs:
        args += ['--input', value]
    r = call(args)
    (reg / (name + '.json')).write_text(json.dumps(r, indent=2, allow_nan=False))
    assert not r.get('warning') and not r.get('conflicting_outputs')
    readback = call(['artifact', 'show', r['artifact']])
    assert readback['output_blob'] == r['output_blob'] == sha(out / name)
    (reg / (name + '.readback.json')).write_text(json.dumps(readback, indent=2, allow_nan=False))
    if not supplement:
        forbidden = {json.loads((out / 'archive-inspection.json').read_text())[k]
                     for k in ['outer_sha256', 'nested_sha256', 'docx_sha256']}
        assert not forbidden.intersection({i['blob'] for i in readback['manifest']['derivation']['inputs']})
    print(name, r['artifact'], 'readback verified')
