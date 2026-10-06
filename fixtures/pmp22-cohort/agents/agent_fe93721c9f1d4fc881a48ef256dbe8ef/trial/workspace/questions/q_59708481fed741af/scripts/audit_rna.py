"""Retrospective RNA endpoint audit; no biological independence assumption."""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

import pyarrow.parquet as pq

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
out = q / 'outputs'
plan = json.loads((q / 'inputs/descriptive-plan.json').read_text())
source = w / 'blobs/sha256/b3/b3d15fe88a6a680290cb57a382ac93c9f5451966d5d20b58bfa2994b0ddcb580'
prepared = w / 'blobs/sha256/a2/a286c57fd32a24a01d5be33fb14c75564c5dc23b4284b5ec57031178895bbac4'
metadata = w / 'blobs/sha256/cc/cc3f098b687c26493f4095548b1f9822259f92ac30f26ef5b5d470b5ec8f924b'
cols = ['LentiAS-1', 'LentiAS-2', 'LentiGFP-1', 'LentiGFP-2']
with source.open() as stream:
    native = list(csv.DictReader(stream, delimiter='\t'))
rows = pq.read_table(prepared).to_pylist()
assert len(rows) == len(native)
for i, (raw, row) in enumerate(zip(native, rows, strict=True), 2):
    assert row['__source_row'] == i
    assert all(row[key] == value for key, value in raw.items())
assert len(set(r['#Geneid'] for r in rows)) == len(rows), 'duplicate symbols: audit before collapsing'
prepared_rows = len(rows)
excluded_rows = [row for row in rows if any(not row[col].isdecimal() for col in cols)]
assert len(excluded_rows) == 1
assert excluded_rows[0]['__source_row'] == 1472 and excluded_rows[0]['#Geneid'] == 'Geneid'
assert [excluded_rows[0][c] for c in cols] == ['LentiAS-1', 'LentiAS-for-RNAseq-2_S49.featureCounts', 'LentiGFP-for-RNAseq-1_S46.featureCounts', 'LentiGFP-for-RNAseq-2_S47.featureCounts']
rows = [row for row in rows if row not in excluded_rows]
values = []
for row in rows:
    tokens = [row[col] for col in cols]
    assert all(token.isdecimal() for token in tokens), 'unexpected count token'
    values.append([int(token) for token in tokens])
sums = [sum(v[j] for v in values) for j in range(4)]
positive = [v for v in values if all(x > 0 for x in v)]
geomeans = [math.exp(statistics.mean(math.log(x) for x in v)) for v in positive]
factors = [statistics.median(v[j] / gm for v, gm in zip(positive, geomeans, strict=True)) for j in range(4)]
by_gene = {row['#Geneid']: (row, v) for row, v in zip(rows, values, strict=True)}

def effect(v):
    as_mean, gfp_mean = statistics.mean(v[:2]), statistics.mean(v[2:])
    return math.log2(as_mean / gfp_mean) if as_mean > 0 and gfp_mean > 0 else None

results = []
for gene in plan['features']:
    if gene not in by_gene:
        results.append({'gene': gene, 'status': 'not_in_supplied_table', 'source_row': None})
        continue
    row, v = by_gene[gene]
    cpm = [v[j] / sums[j] * 1e6 for j in range(4)]
    mr = [v[j] / factors[j] for j in range(4)]
    results.append({'gene': gene, 'status': 'measured_zero_present' if 0 in v else 'measured_positive',
                    'source_row': row['__source_row'], 'description': row['description'],
                    **dict(zip(cols, v, strict=True)), 'raw_log2_AS_over_GFP': effect(v),
                    'CPM_log2_AS_over_GFP': effect(cpm), 'median_ratio_log2_AS_over_GFP': effect(mr)})
keys = ['gene', 'status', 'source_row', 'description', *cols, 'raw_log2_AS_over_GFP', 'CPM_log2_AS_over_GFP', 'median_ratio_log2_AS_over_GFP']
with (out / 'GSE201623-target-audit.tsv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=keys, delimiter='\t')
    writer.writeheader()
    writer.writerows(results)
with (out / 'GSE201623-all-effects.tsv').open('w') as f:
    writer = csv.writer(f, delimiter='\t')
    writer.writerow(['gene', 'source_row', *cols, 'median_ratio_log2_AS_over_GFP', 'CPM_log2_AS_over_GFP'])
    for row, v in zip(rows, values, strict=True):
        mr = effect([v[j] / factors[j] for j in range(4)])
        cpm = effect([v[j] / sums[j] * 1e6 for j in range(4)])
        writer.writerow([row['#Geneid'], row['__source_row'], *v, '' if mr is None else mr, '' if cpm is None else cpm])
# Native sample labels, with explicit unknown donor fields.
samples = []
for block in metadata.read_text().split('^SAMPLE = ')[1:]:
    fields = {}
    lines = block.splitlines()
    for line in lines[1:]:
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            fields.setdefault(key, []).append(value)
    title = fields['!Sample_title'][0]
    label = title.split(' [')[0].replace(' ', '-')
    assert label in cols
    samples.append({'gsm': lines[0], 'column': label, 'title': title, 'organism': fields['!Sample_organism_ch1'][0],
                    'cell_type': 'primary sciatic-nerve Schwann cells', 'assay': 'total RNA-seq',
                    'duration_hours': 48, 'source_dose_token': '2UFC/cell',
                    'biological_replicate_wording': fields['!Sample_extract_protocol_ch1'][0],
                    'donor_id': None, 'donor_independence_verified': False,
                    'assembly': 'Rn6 (Rnor_6.0)', 'count_semantics': 'featureCounts RefSeq gene-assigned counts',
                    'promoter_resolved': False, 'protein_or_activity_measured': False,
                    'metadata_blob': hashlib.sha256(metadata.read_bytes()).hexdigest()})
assert {s['column'] for s in samples} == set(cols)
(out / 'GSE201623-sample-eligibility.json').write_text(json.dumps(samples, indent=2, allow_nan=False) + '\n')
qc = {'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
      'prepared_sha256': hashlib.sha256(prepared.read_bytes()).hexdigest(),
      'source_strings_and_rows_all_exact': True, 'prepared_rows': prepared_rows, 'feature_rows': len(rows), 'globally_positive_rows': len(positive),
      'excluded_nonmeasurement_rows': excluded_rows,
      'column_order': cols, 'column_sums': sums, 'median_ratio_factors': factors,
      'zero_counts_per_column': [sum(v[j] == 0 for v in values) for j in range(4)],
      'labelled_pair_log1p_correlations': {cols[a] + '__' + cols[b]: statistics.correlation([math.log1p(v[a]) for v in values], [math.log1p(v[b]) for v in values]) for a, b in [(0, 1), (2, 3)]},
      'top_ten_count_contributors': {col: [{'gene': rows[i]['#Geneid'], 'count': values[i][j], 'fraction': values[i][j] / sums[j]} for i in sorted(range(len(rows)), key=lambda i: values[i][j], reverse=True)[:10]] for j, col in enumerate(cols)},
      'target_results': results, 'interpretation_limit': 'Descriptive relative steady-state RNA only. No p-values, CIs, independent donors, EGR2 half-life, or Pmp22 initiation inference.'}
(out / 'GSE201623-audit.json').write_text(json.dumps(qc, indent=2, allow_nan=False) + '\n')
print(json.dumps({'validated_rows': len(rows), 'positive_rows': len(positive), 'column_sums': sums,
                  'selected_results': [r for r in results if r['gene'] in {'Egr2', 'Pmp22', 'Jun', 'Sox2'}]}, allow_nan=False))
