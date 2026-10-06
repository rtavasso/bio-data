"""Descriptive human PMP22 audit on immutable primary inputs; no inference over donors."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import platform
import openpyxl

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs/r002'
OUT.mkdir(exist_ok=True)
manifest = json.loads((Q / 'inputs/immutable-inputs.json').read_text())
inputs = {r['relative_path']: r for r in manifest['inputs']}
WS = Path(os.environ['BIO_WORKSPACE']).resolve()


def read(name):
    r = inputs[name]
    # Resolve immutable hashes inside this workspace, not historical absolute paths.
    p = WS / 'blobs/sha256' / r['blob'][:2] / r['blob']
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == r['blob'], name
    assert len(data) == r['bytes'], name
    return data


def write_json(name, value):
    p = OUT / name
    text = json.dumps(value, indent=2, allow_nan=False) + '\n'
    with p.open('x') as f:
        f.write(text)
    assert json.loads(p.read_text()) == value


def write_tsv(name, rows):
    assert rows
    p = OUT / name
    with p.open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        w.writeheader()
        w.writerows(rows)
    with p.open(newline='') as f:
        recovered = list(csv.DictReader(f, delimiter='\t'))
    assert len(recovered) == len(rows)


annotations = json.loads(read('inputs/evidence-annotations.json'))
assert len({c['id'] for c in annotations['contexts']}) == len(annotations['contexts'])
context_rows = []
for c in annotations['contexts']:
    row = dict(c)
    row['source_hashes'] = {name: inputs[name]['blob'] for name in c['files']}
    for name in c['files']:
        read(name)
    assert isinstance(c['eligible_for_cn_function_slope'], bool)
    assert c['human_disease_donors'] is None or c['human_disease_donors'] >= 1
    context_rows.append(row)
write_json('human-evidence-matrix.json', {
    'authorship': annotations['authorship'], 'question': Q.name,
    'checklist': annotations['checklist'], 'contexts': context_rows,
    'warning': 'Do not sum donors across rows: cohorts and lineages overlap. Unknown donor count is null, not zero.'})
flat = []
for c in context_rows:
    flat.append({k: json.dumps(v, ensure_ascii=False, allow_nan=False) if isinstance(v, (list, dict))
                 else 'unknown' if v is None else v for k, v in c.items()})
write_tsv('human-evidence-matrix.tsv', flat)

workbook_name = 'inputs/native/PMC10684506/43856_2023_400_MOESM2_ESM.xlsx'
wb = openpyxl.load_workbook(io.BytesIO(read(workbook_name)), read_only=True,
                           data_only=False, keep_links=False)
raw = []
results = []
checks = []


def values(sheet, coords, group):
    vals = []
    for coord in coords:
        cell = wb[sheet][coord]
        assert cell.data_type == 'n', (sheet, coord, cell.data_type)
        assert isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
        assert math.isfinite(cell.value) and cell.value >= 0
        vals.append(cell.value)
        raw.append({'study': 'PMC10684506', 'sheet': sheet, 'cell': coord,
                    'group': group, 'source_value': cell.value,
                    'cell_type': cell.data_type,
                    'source_sha256': inputs[workbook_name]['blob'],
                    'donor_line': 'HPS0426/CiRA00139',
                    'replicate_id': 'not supplied; no cross-assay pairing assumed'})
    return vals


for sheet, outcome in [('Figure 7d', 'total_mature_RNA'), ('Figure 7e', 'total_protein_WB')]:
    assert wb[sheet]['A15'].value == 'Day 47   PMP22 / GAPDH'
    for r in range(24, 27):
        assert wb[sheet][f'A{r}'].value == 'CMT1A iPSC + control gRNA'
    for r in range(27, 30):
        assert wb[sheet][f'A{r}'].value == 'CMT1A iPSC + edit gRNA'
    cont = values(sheet, [f'B{r}' for r in range(24, 27)], 'AAV-gRNAcont')
    edit = values(sheet, [f'B{r}' for r in range(27, 30)], 'AAV-gRNAedit')
    for label, v, loc in [('control', cont, 'E20'), ('edit', edit, 'E21')]:
        assert math.isclose(statistics.mean(v), wb[sheet][loc].value, rel_tol=1e-12)
        checks.append({'check': 'mean_matches_source', 'sheet': sheet, 'group': label,
                       'mean_cell': loc, 'passed': True})
    cm, em = statistics.mean(cont), statistics.mean(edit)
    ratio = em / cm
    results.append({'outcome': outcome, 'sheet': sheet, 'units': 'relative PMP22/GAPDH',
                    'source_label': wb[sheet]['A15'].value, 'n_control_values': len(cont),
                    'n_edit_values': len(edit), 'disease_donors': 1,
                    'control_mean': cm, 'edited_mean': em, 'edited_over_control': ratio,
                    'log2_ratio': math.log2(ratio), 'percent_change': 100 * (ratio - 1),
                    'direction_rule': 'ratio < 1', 'direction_met': ratio < 1,
                    'unit_limit': 'n values are not donors; batch and RNA/protein pairing IDs absent'})

sheet = 'Figure 6a'
assert wb[sheet]['A5'].value == 'AAV-gRNAcont'
assert wb[sheet]['B5'].value == 'AAV-gRNAedit'
assert wb[sheet]['A3'].value == 'Area% of MBP co-localized with MAP2'
cont = values(sheet, [f'A{r}' for r in range(6, 10)], 'AAV-gRNAcont')
edit = values(sheet, [f'B{r}' for r in range(6, 10)], 'AAV-gRNAedit')
for label, v, loc in [('control', cont, 'E6'), ('edit', edit, 'E7')]:
    assert all(0 <= x <= 100 for x in v)
    assert math.isclose(statistics.mean(v), wb[sheet][loc].value, rel_tol=1e-12)
    checks.append({'check': 'mean_matches_source', 'sheet': sheet, 'group': label,
                   'mean_cell': loc, 'passed': True})
cm, em = statistics.mean(cont), statistics.mean(edit)
ratio = em / cm
results.append({'outcome': 'MBP_MAP2_overlap', 'sheet': sheet, 'units': 'percent',
                'source_label': wb[sheet]['A3'].value, 'n_control_values': len(cont),
                'n_edit_values': len(edit), 'disease_donors': 1,
                'control_mean': cm, 'edited_mean': em, 'edited_over_control': ratio,
                'log2_ratio': math.log2(ratio), 'percent_change': 100 * (ratio - 1),
                'direction_rule': 'ratio > 1', 'direction_met': ratio > 1,
                'unit_limit': 'structural overlap; paper also describes merged neurite length; no conversion between area and length or calibrated functional PMP22'})
wb.close()
write_tsv('within-background-values.tsv', raw)
write_tsv('within-background-summary.tsv', results)
write_json('within-background-summary.json', {
    'study': 'PMC10684506', 'question': Q.name,
    'analysis_status': 'retrospective descriptive source verification, not independent replication',
    'plan_sha256': inputs['inputs/analysis-plan.json']['blob'],
    'workbook_sha256': inputs[workbook_name]['blob'],
    'comparison': 'same CMT1A Schwann background AAV-gRNAedit / AAV-gRNAcont; common normal neuronal background',
    'results': results, 'source_mean_checks': checks,
    'all_planned_directions_met': all(r['direction_met'] for r in results),
    'new_p_values': None, 'new_confidence_intervals': None,
    'copy_number_slope': None,
    'blockers': ['mosaic editing without matched endpoint-sample absolute CN',
                 'one disease donor and no cross-assay replicate or batch mapping',
                 'PMP22/GAPDH ratios not calibrated molecules per viable matched-state Schwann cell',
                 'structural proxy not mature compact-myelin protein or conduction',
                 'maturation, survival, composition and co-deleted genes remain alternatives'],
    'interpretation': 'RNA and total protein decrease by different relative amounts. This does not identify saturation, translational compensation, folding failure, trafficking or degradation rates.'})

# Preserve GSM labels and disagreement, without silently repairing BONb metadata.
geo_name = 'inputs/public/GSE7423-family.txt'
geo = read(geo_name).decode('utf-8')
records = []
current = None
for line_no, native_line in enumerate(geo.split('\n'), 1):
    line = native_line.rstrip('\r')
    if line.startswith('^SAMPLE = '):
        current = {'accession': line.split(' = ', 1)[1], 'source_line': line_no, 'fields': {}, 'view_rows': 0}
        records.append(current)
    elif current is not None and line.startswith(('!', '#')) and ' = ' in line:
        key, value = line.split(' = ', 1)
        current['fields'].setdefault(key, []).append(value)
    elif current is not None and re.match(r'^\d+\t', line):
        current['view_rows'] += 1
rows = []
for rec in records:
    f = rec['fields']
    def field(name, fields=f):
        return ' | '.join(fields.get(name, []))
    chars = field('!Sample_characteristics_ch1')
    m = re.search(r'lab\s*code ([A-Z]+)', chars)
    assert m, rec['accession']
    donor = m.group(1)
    group = 'PMP22_duplication' if 'duplication of the gene' in chars else 'PMP22_Leu16Pro' if 'Leu16Pro' in chars else 'normal' if 'Normal subject' in chars else 'CTDP1'
    rows.append({'accession': rec['accession'], 'source_line': rec['source_line'],
                 'title': field('!Sample_title'), 'donor_labcode': donor, 'group': group,
                 'characteristics_verbatim': chars, 'source_ch1': field('!Sample_source_name_ch1'),
                 'reference_ch2': field('!Sample_characteristics_ch2'),
                 'label_ch1': field('!Sample_label_ch1'), 'label_ch2': field('!Sample_label_ch2'),
                 'VALUE_definition': field('#VALUE'), 'platform': field('!Sample_platform_id'),
                 'declared_feature_rows': int(field('!Sample_data_row_count')),
                 'measurement_rows_in_quick_view': rec['view_rows'],
                 'replicate_label_conflict': donor == 'BON' and 'BONb' in field('!Sample_title') and 'replicate a' in chars,
                 'source_sha256': inputs[geo_name]['blob']})
assert len(rows) == len({r['accession'] for r in rows})
assert {r['donor_labcode'] for r in rows if r['group'] == 'PMP22_duplication'} == {'BAR'}
assert all(r['measurement_rows_in_quick_view'] < r['declared_feature_rows'] for r in rows)
write_tsv('GSE7423-donor-channel-map.tsv', rows)
geo_summary = {'sample_records': len(rows), 'donor_labels': sorted({r['donor_labcode'] for r in rows}),
               'groups': {g: {'arrays': sum(r['group'] == g for r in rows),
                              'donor_labels': sorted({r['donor_labcode'] for r in rows if r['group'] == g})}
                          for g in sorted({r['group'] for r in rows})},
               'metadata_disagreements': [r['accession'] for r in rows if r['replicate_label_conflict']],
               'eligible_dosage_donors': 1, 'expression_analysis_performed': False,
               'limitation': 'Quick-view measurement rows incomplete; donor metadata usable. Mixed reference pool and repeated cultures are not extra donors. No promoter or protein endpoint.'}
write_json('GSE7423-design-summary.json', geo_summary)
write_json('audit-validation.json', {
    'status': 'passed', 'context_rows': len(context_rows), 'numeric_source_cells': len(raw),
    'mean_checks': len(checks), 'GEO_sample_records': len(rows),
    'finite_numeric_values': all(math.isfinite(r['source_value']) for r in raw),
    'formulas_executed': False, 'donor_inferential_statistics_performed': False,
    'input_hashes_validated': True, 'JSON_roundtrip': True,
    'python': sys.version, 'openpyxl': openpyxl.__version__, 'platform': platform.platform()})
print(json.dumps({'results': results, 'GSE7423': geo_summary, 'validation': 'passed'}, indent=2, allow_nan=False))
