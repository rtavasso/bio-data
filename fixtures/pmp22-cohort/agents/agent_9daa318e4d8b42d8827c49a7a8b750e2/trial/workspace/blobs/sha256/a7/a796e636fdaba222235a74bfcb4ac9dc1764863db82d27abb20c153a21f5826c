"""Register completed source-preservation outputs, then verify catalog readback."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
root = w.parent
out = q / 'outputs'
old = w / 'questions/q_277f20df4b6b47cc'
reg = out / 'registrations'
reg.mkdir(exist_ok=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(args):
    result = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def obj(path):
    result = call(['object', 'add', str(path)])
    assert result['blob'] == sha(path)
    return result['blob']


producer = q / 'scripts/export_cis_sources.py'
receipt = out / 'export-execution-r001.json'
execution = json.loads(receipt.read_text())
assert execution['complete'] and execution['exit_code'] == 0 and execution['code_sha256'] == sha(producer)
paths = [old / 'inputs/continuation' / (pmc + '.html') for pmc in ('PMC3298281', 'PMC7322568', 'PMC5181599')]
paths += [receipt, out / 'source-receipts.redacted.json', q / 'inputs/tss-native-profile.json',
          q / 'inputs/tss-archive-profile.json', old / 'outputs/tss-regulatory-panel.tsv']
inputs = [obj(p) for p in paths]
inputs += ['asset_f7b45493c97bcbf69f884f50fb111ee5', 'asset_bfb7964142cde09a93a524f3b7ecb0b0']
for name in sys.argv[1:]:
    expected = next(x for x in execution['outputs'] if Path(x['path']).name == name)
    output = out / name
    assert expected['written'] and sha(output) == expected['sha256']
    args = ['register', str(output), '--question', q.name,
            '--title', 'PMP22 cis-source access GSE139321: ' + name,
            '--summary', 'Exact inherited-source access and locators, no scientific reanalysis.',
            '--code', str(producer), '--output-role', name,
            '--parameters', json.dumps({'operation': 'source-preserving byte export', 'scientific_rerun': False,
                                       'execution_receipt_sha256': sha(receipt)})]
    for value in inputs:
        args += ['--input', value]
    result = call(args)
    (reg / (name + '.json')).write_text(json.dumps(result, indent=2, allow_nan=False))
    assert not result.get('warning') and not result.get('conflicting_outputs')
    check = call(['artifact', 'show', result['artifact']])
    assert check['output_blob'] == result['output_blob'] == sha(output)
    assert any(item['question_id'] == q.name for item in check['questions'])
    (reg / (name + '.readback.json')).write_text(json.dumps(check, indent=2, allow_nan=False))
    print(name, result['artifact'], 'readback verified')
