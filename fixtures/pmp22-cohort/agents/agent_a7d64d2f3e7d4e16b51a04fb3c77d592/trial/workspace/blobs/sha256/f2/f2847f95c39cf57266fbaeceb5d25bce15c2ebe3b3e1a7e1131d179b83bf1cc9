"""Correct narrative component transcription while preserving every numeric measurement."""
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
REV = OUT/'r002'
REV.mkdir(exist_ok=True)


def digest(b):
    return hashlib.sha256(b).hexdigest()


original = OUT/'lipid-feedback-evidence.zip'
reg = json.loads((OUT/'registration/lipid-feedback-evidence.zip.json').read_text())
assert digest(original.read_bytes()) == reg['output_blob']
components = pd.read_csv(OUT/'rna-named-gene-contrasts.tsv', sep='\t')
components = components[components.contrast.isin(['GSE115930_P18','GSE252209_5wk']) & components.symbol.isin(['Abca1','Abcg1'])]
assert len(components) == 4
ratios = pd.read_csv(OUT/'discovery-transporter-split.tsv', sep='\t').set_index('contrast')
for context, frame in components.groupby('contrast'):
    d = frame.set_index('symbol').delta_log2
    assert np.isclose(d['Abca1']-d['Abcg1'], ratios.loc[context,'delta_log2'])
components.to_csv(REV/'component-audit.tsv',sep='\t',index=False)
report = json.loads((OUT/'candidate-feedback-analysis.json').read_text())
report.update(json.loads((Q/'inputs/interpretation-curation.json').read_text()))
report['component_audit'] = json.loads(components.to_json(orient='records'))
report['correction'] = {'supersedes_analysis_post':'post_e56105ff137e44a38629f8cea4c1bd2b',
    'supersedes_analysis_artifact':'artifact_ebde69a87af5705390658ff9f9cdd643417ab50b7a9392852efed6c858f5eab1',
    'error':'P18 component values were transcribed incorrectly in narrative; native and computed tables were correct.',
    'fixed':'P18 Abca1 +1.7577059776; Abcg1 -0.2635820546; latter CI crosses zero.',
    'numeric_tables_unchanged':True,'new_biological_analysis':False,
    'interpretation':'Relative-transporter ratio increase, not separately replicated ABCG1 repression.'}
(REV/'candidate-feedback-analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False))
with zipfile.ZipFile(original) as z:
    files = {n:z.read(n) for n in z.namelist() if n!='source-provenance.json'}
    manifest = json.loads(z.read('source-provenance.json'))
for item in manifest['files']:
    assert digest(files[item['member']]) == item['sha256']
replacements = {'LABBOOK.md':Q/'LABBOOK.md','inputs/interpretation-curation.json':Q/'inputs/interpretation-curation.json',
                'outputs/candidate-feedback-analysis.json':REV/'candidate-feedback-analysis.json',
                'outputs/component-audit.tsv':REV/'component-audit.tsv','scripts/correct_delivery.py':Path(__file__)}
for name,path in replacements.items():
    data = path.read_bytes()
    old = next((x for x in manifest['files'] if x['member']==name),None)
    if old:
        old['prior_sha256'] = old['sha256']
        old.update(sha256=digest(data),bytes=len(data),revision='narrative correction r002')
    else:
        manifest['files'].append({'member':name,'sha256':digest(data),'bytes':len(data),'role':'current_correction_artifact'})
    files[name] = data
manifest['supersedes_bundle_artifact'] = reg['artifact']
manifest['correction'] = report['correction']
(REV/'source-provenance.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
with zipfile.ZipFile(REV/'lipid-feedback-evidence.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items():
        z.writestr(name,data)
    z.writestr('source-provenance.json',json.dumps(manifest,indent=2,allow_nan=False))
with zipfile.ZipFile(REV/'lipid-feedback-evidence.zip') as z:
    assert z.testzip() is None
    assert set(z.namelist()) == set(files)|{'source-provenance.json'}
    for item in manifest['files']:
        assert digest(z.read(item['member'])) == item['sha256']
# Numeric source tables, prior producing receipts and locked prediction remain identical.
with zipfile.ZipFile(original) as old, zipfile.ZipFile(REV/'lipid-feedback-evidence.zip') as new:
    immutable = [n for n in old.namelist() if n.startswith('native/') or n.startswith('outputs/rna-') or n.startswith('outputs/validation-') or n.startswith('outputs/predictions/')]
    assert all(old.read(n)==new.read(n) for n in immutable)
print(json.dumps({'revision':'r002','component_rows':len(components),'unchanged_numeric_and_source_members':len(immutable),'complete_manifest_verified':True}))
