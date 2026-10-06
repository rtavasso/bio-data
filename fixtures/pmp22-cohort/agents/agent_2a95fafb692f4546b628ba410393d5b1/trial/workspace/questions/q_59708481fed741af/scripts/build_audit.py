"""Validate and tabulate agent-curated source evidence; not automated biology extraction."""
import csv
import hashlib
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
curated = json.loads((q / 'inputs/interventions.curated.json').read_text())
rescue = json.loads((q / 'inputs/rescue-test.json').read_text())
rna = json.loads((out / 'GSE201623-audit.json').read_text())
receipt = json.loads((out / 'rna-execution-r002.json').read_text())
assert receipt['complete'] and receipt['exit_code'] == 0 and receipt['code_unchanged']
for product in receipt['outputs']:
    path = Path(product['path'])
    assert product['written'] and hashlib.sha256(path.read_bytes()).hexdigest() == product['sha256']
assert rna['source_strings_and_rows_all_exact']
assert rna['prepared_rows'] == rna['feature_rows'] + len(rna['excluded_nonmeasurement_rows'])
records = curated['interventions']
assert len(set(r['id'] for r in records)) == len(records)
assert all(r['source'] in curated['sources'] for r in records)
assert all(r['locator'] and r['biological_unit'] and r['limitation'] for r in records)
assert all(not r['eligible_for_pmp22_mediation'] for r in records)
assert curated['half_life_hours'] is None and curated['egr2_mediated_fraction_of_pmp22_effect'] is None
fields = list(records[0])
assert all(set(r) == set(fields) for r in records)
with (out / 'intervention-by-endpoint.tsv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
    writer.writeheader()
    writer.writerows(records)
eligibility = {'curated_interventions': records, 'source_index': curated['sources'],
               'missing_prerequisites': curated['missing_prerequisites'],
               'missing_token_rule': 'JSON null or blank TSV means unlocated/not identifiable; never measured zero.',
               'curation_attribution': curated['curator'], 'curation_nature': curated['nature']}
(out / 'assay-eligibility.json').write_text(json.dumps(eligibility, indent=2, allow_nan=False) + '\n')
summary = {'question': q.name, 'result': 'Endpoint-specific non-identifiability of chiefly EGR2-mediated Pmp22 regulation',
           'interventions_audited': len(records),
           'eligible_pmp22_mediation_contrasts': sum(r['eligible_for_pmp22_mediation'] for r in records),
           'reported_egr2_chase_direction_available': any(r['eligible_for_egr2_decay_direction'] for r in records),
           'egr2_half_life_hours': None, 'pmp22_mediated_fraction': None,
           'changed_position': 'Source Figure 8N abundance rescue without MPZ rescue shifts from EGR2-only preference to pleiotropic control with unidentified PMP22 mediation; MG132 nonspecific and EGR2 activity unverified.',
           'retrospective_rna_counterexample': [r for r in rna['target_results'] if r['gene'] in {'Egr2', 'Pmp22', 'Jun'}],
           'rna_rows_verified': rna['prepared_rows'], 'numeric_features': rna['feature_rows'],
           'rescue_design': rescue, 'validation': 'Source-row identity, numeric token audit, source/locator presence, unique intervention IDs, producer output hashes and finite JSON passed.',
           'not_claimed': ['independent replication', 'new molecular mechanism', 'EGR2-specific MG132 rescue', 'no Egr2 RNA contribution', 'human transfer', 'protein abundance from identification scores']}
(out / 'mediation-audit.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
print(json.dumps({k: summary[k] for k in ['interventions_audited', 'eligible_pmp22_mediation_contrasts', 'reported_egr2_chase_direction_available', 'rna_rows_verified', 'numeric_features', 'validation']}))
