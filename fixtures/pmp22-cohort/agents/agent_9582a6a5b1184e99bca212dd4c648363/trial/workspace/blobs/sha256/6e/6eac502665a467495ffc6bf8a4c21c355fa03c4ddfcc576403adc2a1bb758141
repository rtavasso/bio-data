"""Prepare explicit artifact manifests; never fabricate execution receipts."""
import hashlib
import json
from pathlib import Path
import subprocess

P = Path(__file__).resolve().parents[1]
OUT = P / 'outputs'
inputs = json.loads((P / 'sources/immutable-inputs.json').read_text())
bundle = json.loads((OUT / 'evidence-package.json').read_text())
run = json.loads((OUT / 'execution-r002.json').read_text())
assert run['complete'] and run['exit_code'] == 0
assert json.loads((OUT / 'validation.json').read_text())['status'] == 'passed'


def add(path):
    value = json.loads(subprocess.run(['./bin/bio', 'object', 'add', str(path)],
                                     text=True, capture_output=True, check=True).stdout)
    assert value['blob'] == hashlib.sha256(path.read_bytes()).hexdigest()
    return value['blob']


code = add(P / 'scripts/assemble_audit.py')
assert code == run['code_sha256']
references = [add(OUT / 'execution-r002.json'), add(OUT / 'validation.json'),
              add(P / 'scripts/validate_audit.py'), add(P / 'scripts/pdf_text.js')]
derivation = {
    'inputs': [{'blob': v['blob'],
                'role': 'agent_curation' if k == 'curated-evidence.json' else 'source_evidence',
                'selector': {'source_file': k, 'description': 'Exact immutable input; output records retain native locators'}}
               for k, v in inputs.items()],
    'code': [code],
    'parameters': {'analysis': 'retrospective-source-audit', 'new_DE_test': False,
                   'source_sheet': 'TSS- H3K4me3 and SOX10', 'feature_selector': 'Gene Name exactly Pmp22',
                   'focal_cluster_ids': [5439, 5446], 'primer_source': 'Thesis Table2-1 only',
                   'producer_receipt_sha256': references[0]},
    'references': references,
    'environment': bundle['environment'],
    'command': run['argv']
}
products = [
    ('evidence-package.json', 'cis-promoter-audit-bundle', 'PMP22 cis-promoter evidence, identifiability and rat rn5 mapping'),
    ('cis-evidence.tsv', 'cis-evidence-matrix', 'PMP22 source-located cis versus promoter endpoint matrix'),
    ('rat-promoter-map.tsv', 'rat-primer-promoter-map', 'Pmp22 rn5 first-exon primer anchors for GSE139321 clusters'),
    ('pmp22-tss-clusters.tsv', 'tss-cluster-extraction', 'GSE139321 source-preserved selected Pmp22 TSS clusters'),
    ('sample-eligibility.tsv', 'tss-sample-eligibility', 'GSE139321 sample units and cis-nascent assay eligibility')
]
for file, role, title in products:
    manifest = {'title': title, 'summary': 'Bounded audit: steady-state cis evidence is stronger than reporter evidence; nascent/state/dosage mediation is not identified. Includes literal source locators and limitations.',
                'kind': 'json' if file.endswith('.json') else 'tsv', 'output_role': role,
                'limitations': ['Agent-curated evidence rows are interpretation, not new biological data',
                                'Tn5Prime is total-RNA start abundance, not nascent synthesis',
                                'No human coordinate transfer or donor independence assumed',
                                'Some sources available only as abstracts; thesis chapter3 is draft, not final publication'],
                'derivation': derivation}
    (OUT / (file + '.manifest.json')).write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
print(json.dumps({'manifests': len(products), 'inputs': len(inputs), 'producer_code': code,
                  'execution_receipt': references[0]}))
