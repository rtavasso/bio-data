"""Inspect fetched artifact derivation, not its producer code."""
import json
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
for name in ['selective-gene-artifact-fetched.json', 'artifact_77331014c88a4d8da77add923216f59ec27fca413c2645732f895b484c172088.json']:
    obj = json.loads((Q / 'outputs' / name).read_text())
    print('ARTIFACT', obj['id'], 'path', obj['path'], 'output_blob', obj['output_blob'])
    print('DERIVATION INPUTS', json.dumps(obj['manifest']['derivation'].get('inputs'), indent=2))
    print('PARAMETERS', json.dumps(obj['manifest']['derivation'].get('parameters'), indent=2))
    for key, value in obj['manifest'].items():
        if key != 'inputs':
            print(key, json.dumps(value)[:2200])
        else:
            print('INPUTS', json.dumps(value, indent=2))
