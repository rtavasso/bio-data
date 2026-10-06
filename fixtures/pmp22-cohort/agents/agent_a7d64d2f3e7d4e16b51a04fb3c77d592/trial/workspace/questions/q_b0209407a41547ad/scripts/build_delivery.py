"""Assemble validated results and exact static inputs; not a new biological analysis."""
import hashlib
import json
from pathlib import Path
import zipfile

import pandas as pd

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
def sha(data):
    return hashlib.sha256(data).hexdigest()

curation = json.loads((Q/'inputs/interpretation-curation.json').read_text())
program = pd.read_csv(OUT/'rna-program-contrasts.tsv', sep='\t')
ratios = pd.read_csv(OUT/'discovery-transporter-split.tsv', sep='\t')
validation = json.loads((OUT/'validation-transfer.json').read_text())
samples = pd.read_csv(OUT/'source-contrast-map.tsv', sep='\t')
for name in ['rna-execution-r001.json','rna-summary-execution-r001.json','transfer-execution-r001.json']:
    receipt = json.loads((OUT/name).read_text())
    assert receipt['complete'] and receipt['exit_code'] == 0 and receipt['code_unchanged']
    assert sha(Path(receipt['producer']).read_bytes()) == receipt['code_sha256']
    for item in receipt['outputs']:
        assert item['written'] and sha(Path(item['path']).read_bytes()) == item['sha256']
assert '7 passed' in (OUT/'test-results-r002.txt').read_text()
assert 'All checks passed' in (OUT/'lint-results-r002.txt').read_text()
report = {**curation, 'new_computation': {'discovery_native_libraries': len(samples), 'discovery_contrasts': int(program.contrast.nunique()),
          'program_estimates': json.loads(program.to_json(orient='records')),
          'transporter_split': json.loads(ratios.to_json(orient='records')),
          'contextual_transfer': validation},
          'tests': {'assertions': 'seven saved-output consistency tests passed; Ruff passed', 'independent_biology': False},
          'uncertainty': 'Welch intervals conditional on labelled libraries, no independence/pairing invented. Exact permutations are conditional label checks, not proof of randomized assignment.'}
(OUT/'candidate-feedback-analysis.json').write_text(json.dumps(report, indent=2, allow_nan=False))
# A complete, explicit endpoint map distinguishes new measurements from inherited source claims.
rows = []
for context, group in samples.groupby('contrast'):
    for endpoint in ['sterol_synthesis','efflux_export','uptake_transport','fatty_acid_synthesis','myelin7','Pmp22']:
        rows.append({'source': group.accession.iloc[0], 'context': context, 'endpoint': endpoint,
                     'measurement': 'native processed gene RNA counts; program is mean log2 expression', 'role': 'new_computation',
                     'units': 'log2 normalized-count difference (perturbed minus control)', 'paired_to_protein': False,
                     'limitation': 'bulk nerve; no flux or promoter initiation; transgene-inclusive Pmp22 recovery unresolved'})
for source, context, endpoint, limitation in [
    ('PMC6607759','10-month ABCA1-deficient mouse sciatic nerve; Figure4D-G','total PMP22 and EndoH-resistant fraction','Not paired absolute mature/surface abundance; no product of means computed'),
    ('PMC6607759','neonatal-rat-derived Schwann pooled PMP22 shRNA; Figure6H/7C','cholesterol efflux and surface ABCA1','Different species/intervention/preparation from adult ABCA1 knockout'),
    ('PMC11660526','six-week Acly cKO sciatic nerves; separate from five-week RNA','untargeted lipid classes','Primary report only; local sample-level lipid matrix unavailable'),
    ('PMC6072747','dietary phospholipid supplementation in CMT1A rats','myelin lipid composition and functional endpoints','Primary report only; inspected supplementary tables are not lipid matrix'),
    ('PMC13042600','Fdft1 conditional Schwann culture versus adult inducible injury contexts','synthesis perturbation source inventory','Inherited gap is not global data absence; rat GSE216665 injury is not knockout')]:
    rows.append({'source':source,'context':context,'endpoint':endpoint,'measurement':'primary source report / inherited audit',
                 'role':'not_new_quantitative_measurement','units':'native source-specific; no combined scale','paired_to_protein':False,'limitation':limitation})
pd.DataFrame(rows).to_csv(OUT/'source-contrast-endpoint-map.tsv', sep='\t', index=False)
files, provenance = {}, []


def add(member, path, role, **extra):
    path = Path(path)
    assert not member.startswith('/') and '..' not in Path(member).parts
    b = path.read_bytes()
    assert member not in files
    files[member] = b
    provenance.append({'member': member, 'sha256': sha(b), 'bytes': len(b), 'role': role, **extra})


for path in sorted((Q/'inputs').iterdir()):
    if path.is_file():
        role = 'agent_authored_specification' if path.name in ['analysis-plan.json','interpretation-curation.json'] else 'current_transport_or_inspected_source_bytes'
        add('inputs/'+path.name,path,role,receipt='inputs/'+path.name+'.receipt.json' if path.with_name(path.name+'.receipt.json').exists() else None)
for label, source in [('Acly','GSE252209'),('CMT','GSE115930'),('Acly-deg','GSE252209-author-DE')]:
    meta = json.loads((OUT/f'{label}-acquired.json').read_text())
    add('native/'+source+'.tsv-or-csv.gz',meta['path'],'newly_acquired_native_processed',source=source)
for row in validation['samples']:
    h = row['source_blob']
    p = Q.parents[1]/'blobs/sha256'/h[:2]/h
    assert sha(p.read_bytes()) == h
    add('native/'+row['source_file'],p,'inherited_native_processed_not_inherited_computation',source='GSE104324',source_artifact='artifact_2ecfb28855342b9e22f37d7d1255c2a5898b91246ac231bdd658600fab11105e')
obj = json.loads((OUT/'artifact_77331014c88a4d8da77add923216f59ec27fca413c2645732f895b484c172088.json').read_text())
assert sha(Path(obj['path']).read_bytes()) == obj['output_blob']
with zipfile.ZipFile(obj['path']) as z:
    member = 'sources/PMC6607759.html'
    b = z.read(member)
    locator = json.loads(z.read('source-locator-manifest.json'))
    entry = next(x for x in locator['files'] if x['member'] == member)
    assert sha(b) == entry['sha256']
    name = 'inherited/PMC6607759.html'
    files[name] = b
    provenance.append({'member':name,'sha256':sha(b),'bytes':len(b),'role':'inherited_primary_HTML_verified_currently','artifact':obj['id']})
# Preserve sample metadata and original peer discovery/transport receipts exactly.
for entry in json.loads((OUT/'peer-input-inventory.json').read_text()):
    if entry['prefix'].startswith('{') and entry['blob'] != '6a69de9578a208fc92c8b8069261c1e5b2ade8559f8b41247f3eb6de4dac2a1c':
        add('inherited/context/'+entry['blob']+'.json',entry['path'],'inherited_metadata_or_receipt')
selected_outputs = [
    'candidate-feedback-analysis.json','source-contrast-endpoint-map.tsv','source-contrast-map.tsv',
    'rna-program-contrasts.tsv','rna-all-gene-contrasts.tsv.gz','rna-per-sample.tsv','rna-named-gene-contrasts.tsv','rna-sensitivities.tsv','rna-eligibility.tsv','rna-qc.tsv','rna-validation.json',
    'validation-transfer.json','validation-per-sample.tsv','validation-native-counts.tsv.gz','validation-sample-map.tsv','discovery-transporter-split.tsv','Acly-group-mapping-validation.json',
    'rna-execution-r001.json','rna-summary-execution-r001.json','transfer-execution-r001.json','test-results.txt','lint-results.txt','test-results-r002.txt','lint-results-r002.txt',
    'Acly-fetch.json','Acly-acquired.json','CMT-fetch.json','CMT-acquired.json','Acly-deg-fetch.json','Acly-deg-acquired.json','GSE252209-metadata.json','GSE115930-metadata.json','GSE252209-sample-metadata.json','GSE115930-sample-metadata.json',
    'selective-gene-artifact-fetched.json','peer-input-inventory.json','supplement-inventory.json','novelty-pmp22-abcg1.json','novelty-acly-schwann.json','gap-acly-lipidomics.json','gap-fledrich-lipidomics.json','proposal.md','proposal-receipt.json']
for name in selected_outputs:
    add('outputs/'+name,OUT/name,'current_result_or_provenance')
add('outputs/predictions/abca1-abcg1-state-transfer-r001.json',OUT/'predictions/abca1-abcg1-state-transfer-r001.json','sealed_prevalidation_prediction')
for p in sorted((Q/'scripts').glob('*.py')):
    add('scripts/'+p.name,p,'current_agent_authored_code_not_executed_by_consumer')
add('LABBOOK.md',Q/'LABBOOK.md','current_notebook_snapshot')
manifest = {'question': Q.name, 'files':provenance,'untrusted_data':True,'no_automatic_code_execution':True,
            'native_safety':'No downloaded code/macros/formulas/pickle/R objects executed. XLSX inspected with formula evaluation disabled.',
            'dependency_note':'All external native data copied to native/ or inherited/; original metadata paths are preserved as historical source receipts, not current host assumptions.'}
(OUT/'source-provenance.json').write_text(json.dumps(manifest, indent=2, allow_nan=False))
with zipfile.ZipFile(OUT/'lipid-feedback-evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,b in files.items():
        z.writestr(name,b)
    z.writestr('source-provenance.json',json.dumps(manifest,indent=2,allow_nan=False))
with zipfile.ZipFile(OUT/'lipid-feedback-evidence.zip') as z:
    assert z.testzip() is None
    assert set(z.namelist()) == set(files)|{'source-provenance.json'}
    for item in provenance:
        assert sha(z.read(item['member'])) == item['sha256']
print(json.dumps({'files':len(files),'zip_bytes':(OUT/'lipid-feedback-evidence.zip').stat().st_size,'manifest_verified':True,'discovery_libraries':len(samples),'validation':validation['result_status']}))
