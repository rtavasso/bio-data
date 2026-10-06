"""Verify eligibility/sample designs and compile attributed causal curation.
No inherited code execution, expression reanalysis, causal model fitting, or RDS loading.
"""
import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import openpyxl

Q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
W = Path(os.environ['BIO_WORKSPACE'])
O = Q / 'outputs'
INPUTS = {}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path, role):
    path = Path(path)
    h = sha(path)
    INPUTS[str(path)] = {'path': str(path), 'sha256': h, 'role': role, 'bytes': path.stat().st_size}
    return path


def blob(h, role):
    path = W / 'blobs/sha256' / h[:2] / h
    assert sha(path) == h, path
    return record(path, role)


def load(path, role='curation'):
    return json.loads(record(path, role).read_text())


def tsv(name, rows, fields=None):
    fields = fields or list(rows[0])
    with (O / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def soft(path):
    record(path, 'source_metadata')
    fields = {}
    for line in path.read_text().splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            fields.setdefault(key, []).append(value)
    return fields


curation = load(Q / 'inputs/causal-curation.json')
plan = load(Q / 'inputs/epistasis-plan.json')
for row in curation['evidence']:
    path = record(Q / row['source'], 'primary_source')
    if path.suffix == '.xml':
        root = ET.parse(path).getroot()
        text = ' '.join(root.itertext())
        row['article_ids'] = {e.get('pub-id-type'): ''.join(e.itertext()) for e in root.findall('./front/article-meta/article-id')}
    else:
        text = path.read_text()
    assert ' '.join(row['anchor'].split()) in ' '.join(text.split()), (row['id'], row['anchor'])
    row['source_sha256'] = sha(path)
    row['assessment_type'] = 'agent_curated_from_source_not_an_experimental_result'
assert len({r['id'] for r in curation['evidence']}) == len(curation['evidence'])
assert not any(r['pmp22_mediation_eligible'] for r in curation['evidence'])

# Extract library labels without converting them into biological donors.
samples = []
for pattern, study in [('GSM772*.soft', 'GSE241269'), ('GSM963*.soft', 'GSE326641')]:
    for path in sorted((Q / 'inputs/public').glob(pattern)):
        d = soft(path)
        ch = dict(v.split(': ', 1) for v in d['!Sample_characteristics_ch1'] if ': ' in v)
        samples.append({'study': study, 'sample': d['!Sample_geo_accession'][0],
                        'title_raw': d['!Sample_title'][0], 'genotype_raw': ch.get('genotype'),
                        'tissue': ch.get('tissue'), 'cell_type': ch.get('cell type', 'whole nerve bulk'),
                        'batch': ch.get('batch'), 'donor_id': None, 'pool_id': None,
                        'independent_donor_confirmed': False,
                        'treatment_raw': ch.get('treatment'),
                        'units': 'RSEM expected counts/TPM/FPKM' if study == 'GSE241269' else "10x 3-prime gene-count matrix described; only RDS listed",
                        'source_sha256': sha(path)})
assert len(samples) == 16
nae_samples = [r for r in samples if r['study'] == 'GSE241269']
assert Counter(r['genotype_raw'] for r in nae_samples) == {'WT': 4, 'Nae1 cKO': 4}
skin = [r for r in samples if r['study'] == 'GSE326641']
skin_batch2 = [r for r in skin if r['batch'] == '2']
assert len(skin_batch2) == 4
skin_design = {'samples': skin, 'batch2_raw_genotypes': dict(Counter(r['genotype_raw'] for r in skin_batch2)),
               'biological_replicates_established': False,
               'notes': ['One library per factorial genotype in batch 2; cells are not donors.',
                         'SUMO2_Ctrl title has SUMO2_KO genotype and reciprocal swap in SUMO2_KO title; not repaired.',
                         'Double knockout title NEF2_KO is preserved; genotype field separately says NEDD8_NRF2_KO.',
                         'Skin/K14 context and gene-level 3-prime RNA cannot identify Schwann Nae1/PMP22 nascent mediation.',
                         'Processed RDS not acquired; no pickle/R code or serialization executed.']}
tsv('sample-assay-eligibility.tsv', samples)

# Audit original frozen floor and literal measured status, not a new panel.
genes = ['Nqo1', 'Hmox1', 'Gclc', 'Gclm', 'Osgin1', 'Pmp22', 'Mpz', 'Mbp', 'Mag', 'Prx', 'Plp1', 'Cnp', 'Mal']
lock = load(blob('85de99cb1c385a5b72eb0eccec4cf5be21b58a87ea0f9df2472c78f2b1b0c11f', 'original_prediction'))
locked = load(blob('db7b127380de3baed45a9838d15cc66094f69e16595cd2dbb78bb4b8e4ce3a8a', 'prior_locked_result'))
posthoc = load(blob('6457898efbf1ee5080bbdd18679ef2032c25f2e6318fbc5a87d1e93f0800a104', 'prior_retrospective_result'))
assert locked['status'] == 'untestable' and not locked['criteria']['eligible']
assert posthoc['status'] == 'retrospective_exploratory_not_validation'
count_path = blob('2d6f0b558d32cd63d89f9799882ed9cb084400aca6cd3b000b5cfdd2cf91673a', 'prepared_count_matrix')
with count_path.open() as f:
    selected = [r for r in csv.DictReader(f, delimiter='\t') if r['symbol'] in genes]
assert len(selected) == len(genes)
wt = [r['title_raw'] for r in nae_samples if r['genotype_raw'] == 'WT']
assert len(wt) == 4
floor_rows = []
for r in selected:
    values = [float(r[c]) for c in wt]
    floor_rows.append({'study': 'Nae1KO', 'gene': r['symbol'], 'measurement_status': 'measured',
                       'native_status': 'no exported status flags', 'baseline_units': 'RSEM expected counts',
                       'baseline_samples': json.dumps(wt), 'baseline_values': json.dumps(values),
                       'baseline_min': min(values), 'locked_floor': 10, 'eligible': all(v >= 10 for v in values),
                       'source_blob': sha(count_path), 'selector': r['gene_id']})
# Verify the selected prepared values against immutable original gene quantification.
native = {
 'WT_K1':'c45d82d4dde6e7800bb107696f7f2a939ccddb9a1742a5f74c2c99e2eba6fb62',
 'KO_K2':'bb366b5cf400286cf8c22854c064cbdaf5a06085a85f96aa0e8d6c75498f7d9a',
 'KO_L1':'8e5695f911223deeafe42b96a1316a4cbf83049ac965805deff9f159eb7acdc4',
 'WT_L3':'72e88c6e0a6e9198e4c81baa01cec75a0c03ef06332060e9d1e83efffcfe14ad',
 'WT_L4':'dfb11dd3c12e8354f0bdde8f230ff2e117f0a623b94d89da152eed4e40e26473',
 'KO_L5':'a87edeaf32110f77c70d0e07254ee771973718b6167fb18537b1215695586583',
 'KO_L8':'bd3b267a01517d3030f9f025a7d64d4a7f7eeaebdeac6aebd22692399fd1ead5',
 'WT_L9':'ac2cdc30317647b371729891f74406b68e8a20e23a4af0649566654c800ef2ce'}
by_id = {r['gene_id']: r for r in selected}
verified_cells = 0
for sample, h in native.items():
    with gzip.open(blob(h, 'native_RSEM'), 'rt') as f:
        rows = [r for r in csv.DictReader(f, delimiter='\t') if r['gene_id'] in by_id]
    assert len(rows) == len(genes)
    for r in rows:
        assert float(r['expected_count']) == float(by_id[r['gene_id']][sample])
        verified_cells += 1

workbook_path = blob('3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6', 'native_Figlia_workbook')
with workbook_path.open('rb') as f:
    wb = openpyxl.load_workbook(f, read_only=True, data_only=False, keep_links=False)
    for group in ['TSC1KO', 'PTENKO', 'RaptorKO']:
        sheet = wb['Control vs ' + group]
        it = sheet.iter_rows(values_only=True)
        header = next(it)
        gi = header.index('gene_name')
        rows = [dict(zip(header, r)) for r in it if r[gi] in genes]
        assert len(rows) == len(genes)
        for r in rows:
            assert not any(isinstance(v, str) and v.startswith('=') for v in r.values())
            vals = [float(r['Dev'+str(i)+' [normalized count]']) for i in [1, 2, 3]]
            present = str(r['isPresent']).upper() == 'TRUE'
            floor_rows.append({'study': group, 'gene': r['gene_name'], 'measurement_status': 'measured',
                               'native_status': str(r['isPresent']), 'baseline_units': 'source normalized counts',
                               'baseline_samples': json.dumps(['Dev1', 'Dev2', 'Dev3']), 'baseline_values': json.dumps(vals),
                               'baseline_min': min(vals), 'locked_floor': 10, 'eligible': present and all(v >= 10 for v in vals),
                               'source_blob': sha(workbook_path), 'selector': 'Control vs '+group+'; gene_name='+r['gene_name']})
    wb.close()
failed = [r for r in floor_rows if not r['eligible']]
assert any(r['gene'] == 'Osgin1' for r in failed)
tsv('locked-panel-eligibility.tsv', floor_rows)
prior = {'original_status': locked['status'], 'posthoc_status': posthoc['status'],
         'native_selected_count_cells_verified': verified_cells, 'ineligible_rows': failed,
         'reported_not_recomputed_effects': [r for r in posthoc['panels'] if r['panel'] in ['eligible4', 'discovery_gene_excluded', 'Pmp22', 'Pmp22_relative']],
         'interpretation': 'Retrieval/eligibility verification, not independent replication; original lock remains untestable; Osgin1 selected out, not absent or biological zero.',
         'mapping_limit': locked['mapping']}

# Read discovery responses and report bounded coverage, not universal absence.
searches = []
for path in sorted((Q/'inputs/public').glob('search-*.json')):
    if path.name.endswith('-receipt.json'):
        continue
    d = load(path, 'search_response')
    searches.append({'source': str(path.relative_to(Q)), 'query': d.get('request', {}).get('queryString'),
                     'hit_count': d.get('hitCount'), 'returned_count': len(d.get('resultList', {}).get('result', [])),
                     'sha256': sha(path),
                     'note': 'Discovery only; no-hit does not show biological absence; broad non-exhaustive queries not negative evidence.'})
for path in sorted((Q/'inputs/public').glob('geo-direct-*.json')):
    if path.name.endswith('-receipt.json'):
        continue
    d = load(path, 'GEO_search_response')['esearchresult']
    searches.append({'source': str(path.relative_to(Q)), 'query': d.get('querytranslation'),
                     'hit_count': int(d['count']), 'returned_count': len(d['idlist']),
                     'ids': d['idlist'], 'sha256': sha(path)})
summary = load(Q/'inputs/public/geo-candidate-summaries.json', 'GEO_candidate_identity')['result']
assert summary['100000081']['accession'] == 'GPL81'
assert summary['200326641']['accession'] == 'GSE326641'
search_decision = {'searches': searches, 'GEO_decision': {'100000081': 'GPL81 platform annotation, not a Schwann/NRF2 experiment',
 '200326641': 'Actual skin Nedd8/NRF2 genetic design; metadata-audited, excluded for current endpoint/context'},
 'stopping_rule': 'No eligible matched Schwann/Nae1-by-Nrf2/Pmp22 nascent design established. Do not acquire broader expression matrices merely for signature similarity.'}
spatial = soft(Q/'inputs/public/GSE326639.soft')
assert spatial['!Series_title'][0].endswith('[Xenium]')
private_path = record(Q/'inputs/public/GSE326642.soft', 'failed_metadata_response_HTML')
assert 'currently private' in private_path.read_text()
search_decision['additional_candidates'] = {
    'GSE326639': 'Related skin K14/Nedd8/Nrf2 spatial study, fixed tissue directly after recombination or 14 days post wounding. Xenium is not a calibrated PMP22 nascent assay and perturbation is not Schwann-targeted; no raw tar acquisition justified.',
    'GSE326642': 'Adjacent-accession discovery attempt returned private HTML, despite HTTP 200 and .soft filename; not evidence for any study design or sibling relationship.'}

# Preserve actual source receipts as references for every retrieved source.
for path in sorted((Q/'inputs/public').glob('*-receipt.json')):
    record(path, 'retrieval_receipt')
# Preserve all series metadata that informed exclusions.
for path in sorted((Q/'inputs/public').glob('GSE*.soft')):
    record(path, 'series_metadata')

# Assemble output. Curated scientific judgments remain explicitly attributed.
audit = {'schema': 'question-local-causal-audit-v1', 'question': curation['question'],
         'curation': curation, 'prior_eligibility_verification': prior, 'samples': samples,
         'skin_design_audit': skin_design, 'discovery_audit': search_decision,
         'epistasis_plan': plan, 'inputs': list(INPUTS.values()),
         'execution_scope': 'New source/metadata and eligibility audit only; no causal model, signature scan, wet-lab or new independent biological replication.',
         'environment': {'python': sys.version, 'openpyxl': openpyxl.__version__}}
(O/'causal-evidence-audit.json').write_text(json.dumps(audit, indent=2, allow_nan=False))
tsv('epistasis-decision-table.tsv', plan['rows'])
tsv('source-locators.tsv', [{'id':r['id'], 'source':r['source'], 'sha256':r['source_sha256'],
                            'locator':r['locator'], 'eligible':r['pmp22_mediation_eligible'], 'reason':r['reason']} for r in curation['evidence']])
(O/'audit-inputs.json').write_text(json.dumps(list(INPUTS.values()), indent=2, allow_nan=False))
print(json.dumps({'evidence_rows': len(curation['evidence']), 'samples': len(samples),
                  'eligibility_rows': len(floor_rows), 'ineligible': [{'study':r['study'],'gene':r['gene'],'baseline_min':r['baseline_min']} for r in failed],
                  'native_count_cells_verified':verified_cells, 'skin_batch2':skin_design['batch2_raw_genotypes'],
                  'eligible_PMP22_mediation_designs':0}, indent=2, allow_nan=False))
