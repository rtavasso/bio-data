"""Retrospective stress-source verification and endpoint eligibility, not raw processing."""
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / 'inputs' / 'public'
OUT = ROOT / 'outputs'
OUT.mkdir(exist_ok=True)
PLAN = json.loads((ROOT / 'inputs' / 'analysis-plan-r001.json').read_text())
PANEL = PLAN['control_panel']


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, allow_nan=False, ensure_ascii=False) + '\n')


def table(name, rows):
    assert rows
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader()
        w.writerows(rows)


def soft(series):
    result = []
    current = None
    for line in (PUB / (series + '.soft')).read_text().splitlines():
        if line.startswith('^SAMPLE = '):
            current = {'accession': line.split(' = ', 1)[1], 'series': series}
            result.append(current)
        elif line.startswith('^'):
            current = None
        elif current is not None and line.startswith('!Sample_'):
            key, value = line.split(' = ', 1)
            current.setdefault(key.removeprefix('!Sample_'), []).append(value)
    return result


def read_matrix(name, delimiter='\t'):
    with gzip.open(PUB / name, 'rt') as f:
        rows = list(csv.reader(f, delimiter=delimiter))
    columns = rows[0][1:]
    genes = [r[0] for r in rows[1:]]
    assert len(genes) == len(set(genes)), 'Ambiguous duplicated gene labels'
    mat = np.array([r[1:] for r in rows[1:]], dtype=float)
    assert mat.shape == (len(genes), len(columns))
    assert np.isfinite(mat).all() and (mat >= 0).all()
    return genes, columns, mat


samples = []
for series in ['GSE118660', 'GSE90070', 'GSE103667']:
    for raw in soft(series):
        title = raw['title'][0]
        chars = raw.get('characteristics_ch1', [])
        row = {'series': series, 'accession': raw['accession'], 'title': title,
               'organism': '|'.join(raw.get('organism_ch1', [])),
               'source_name': '|'.join(raw.get('source_name_ch1', [])),
               'characteristics_verbatim': '|'.join(chars),
               'library_strategy_verbatim': '|'.join(raw.get('library_strategy', [])),
               'donor_id': None, 'independent_culture_id': None,
               'pair_id': None, 'source_column': None,
               'source_locator': f'{series}.soft / {raw["accession"]}'}
        if series == 'GSE90070':
            condition, assay, replicate = title.rsplit('_', 2)
            cols = [x.split(': ', 1)[1] for x in raw['description'] if x.startswith('Sample name: ')]
            assert len(cols) == 1
            row.update(condition=condition, assay=assay, replicate_label=replicate,
                       source_column=cols[0], pair_id=condition + '_' + replicate,
                       pairing_evidence='GEO overall_design: RNA of every sample separated into Input and polysome',
                       dose_nM=400, dose_source='PMC5730339 Methods P31',
                       endpoint='cytosolic RNA' if assay == 'In' else 'RNA in >4-ribosome fractions',
                       caveat='Four labelled replicates per condition; independent culture/donor IDs not supplied; not a footprint assay')
        elif series == 'GSE103667':
            condition, assay, replicate = title.split('_')
            row.update(condition=condition, assay=assay, replicate_label=replicate,
                       pair_id=condition + '_' + replicate,
                       pairing_evidence='PMC6359928 P58: lysate supernatant split for RPF and RNA libraries; labels align',
                       dose_nM=1000 if condition == 'THAP' else 0,
                       endpoint='RNA abundance' if assay == 'RNAseq' else 'ribosome footprints',
                       caveat='Contradictory cell-type field says human embryonic kidney; organism/NIH3T3/mm9/paper support mouse fibroblasts, preserved not silently repaired')
        else:
            if title.startswith('PERK'):
                genotype = 'KO' if 'PERK -/-' in title else 'WT'
                treatment = next(x.split(': ', 1)[1] for x in chars if x.startswith('treatment: '))
                column = 'PERK_' + genotype + '_' + treatment
                dose = 1000
            else:
                treatment = next(x.split(': ', 1)[1] for x in chars if x.startswith('treatment: '))
                column = 'NIH3T3_' + ('Cont' if treatment == 'Control' else treatment)
                dose = 200
            row.update(condition=treatment, assay='RPF', replicate_label=None, source_column=column,
                       dose_nM=dose, dose_source='PMC6416471 Methods Par53', endpoint='relative ribosome footprints',
                       pairing_evidence='No matched total RNA sample in this series inventory',
                       caveat='One library/condition; RNA-Seq strategy/generic extraction text does not establish matched RNA; NIH3T3 late time 7h per GEO/paper')
        samples.append(row)
table('sample-assay-eligibility.tsv', samples)

# Whole-universe footprint verification: no biological-replication inference at n=1.
footprints = []
foot_summary = []
for cell, base, treated in [('MEF', 'PERK_WT_Control', ['PERK_WT_Tg1hr', 'PERK_WT_Tg2hr', 'PERK_WT_Tg5hr', 'PERK_WT_Tg8hr']),
                            ('3t3', 'NIH3T3_Cont', ['NIH3T3_Tg2hr', 'NIH3T3_Tg7hr'])]:
    genes, cols, tpm = read_matrix(f'GSE118660_{cell}_tpm.txt.gz')
    genes2, cols2, count = read_matrix(f'GSE118660_{cell}_count.txt.gz')
    assert genes == genes2 and cols == cols2
    source_cols = {r['source_column'] for r in samples if r['series'] == 'GSE118660'}
    assert set(cols) <= source_cols
    b = cols.index(base)
    ti = genes.index('Pmp22')
    for tr in treated:
        j = cols.index(tr)
        eligible = (count[:, [b, j]] >= 10).all(axis=1) & (tpm[:, [b, j]] >= 4).all(axis=1)
        other = eligible & (np.array(genes) != 'Pmp22')
        ratio = np.log2(count[other, j] / count[other, b])
        median_shift = float(np.median(ratio))
        cpm_shift = math.log2(count[:, j].sum() / count[:, b].sum())
        target_row = None
        for i, gene in enumerate(genes):
            if eligible[i] or gene in PANEL:
                native = float(math.log2(tpm[i, j] / tpm[i, b])) if min(tpm[i, j], tpm[i, b]) > 0 else None
                raw_lfc = float(math.log2(count[i, j] / count[i, b])) if min(count[i, j], count[i, b]) > 0 else None
                row = {'cell': cell, 'contrast': tr + '/' + base, 'gene': gene, 'eligible': bool(eligible[i]),
                       'control_tpm': float(tpm[i,b]), 'stress_tpm': float(tpm[i,j]),
                       'control_expected_count': float(count[i,b]), 'stress_expected_count': float(count[i,j]),
                       'native_tpm_log2': native, 'expected_count_cpm_log2': None if raw_lfc is None else raw_lfc-cpm_shift,
                       'expected_count_median_log2': None if raw_lfc is None else raw_lfc-median_shift,
                       'in_control_panel': gene in PANEL}
                footprints.append(row)
                if gene == 'Pmp22':
                    target_row = row.copy()
        assert target_row is not None
        target_row.update(feature_rows=len(genes), eligible_background=int(other.sum()),
                          fractional_expected_count_cells=int(np.count_nonzero(count != np.floor(count))),
                          no_p_value='n=1 per time/condition; genes are background features, not biological replicates')
        bg_tpm = np.log2(tpm[other, j] / tpm[other, b])
        target_row['native_background_median_log2'] = float(np.median(bg_tpm))
        target_row['relative_to_background_median_log2'] = target_row['native_tpm_log2'] - float(np.median(bg_tpm))
        target_row['eligible_background_percentile'] = float(100*np.mean(bg_tpm <= target_row['native_tpm_log2']))
        foot_summary.append(target_row)
table('footprint-background-audit.tsv', footprints)

# Relative fraction interaction with genuine within-preparation assay pairing only.
genes, cols, mat = read_matrix('GSE90070_dataCount.csv.gz', ',')
meta = {r['source_column']: r for r in samples if r['series'] == 'GSE90070'}
assert set(cols) == set(meta)
assert all(float(x).is_integer() for x in mat.flat)
ti = genes.index('Pmp22')
not_target = np.array(genes) != 'Pmp22'
assays = {a: [i for i,c in enumerate(cols) if meta[c]['assay'] == a] for a in ['In','H']}
pairs = defaultdict(dict)
for i,c in enumerate(cols):
    r = meta[c]
    pairs[(r['condition'], r['replicate_label'])][r['assay']] = i
assert all(set(pair) == {'H','In'} for pair in pairs.values())
conditions = ['Ctrl','Tg1','Tg16','Tg16+PERKi']
assert all(sum(k[0] == c for k in pairs) == 4 for c in conditions)


def size_factors(indices):
    x = mat[:,indices]
    good = (x > 0).all(axis=1) & not_target
    gm = np.exp(np.log(x[good]).mean(axis=1))
    sf = np.median(x[good] / gm[:,None], axis=0)
    sf /= np.exp(np.log(sf).mean())
    return sf, int(good.sum())


joint_sf, joint_n = size_factors(list(range(len(cols))))
separate_sf = np.ones(len(cols))
norm_features = {}
for a, ix in assays.items():
    separate_sf[ix], norm_features[a] = size_factors(ix)
cpm_sf = mat.sum(axis=0)/1e6
norm = {'assay_separate_median_ratio': separate_sf, 'joint_median_ratio': joint_sf, 'CPM': cpm_sf}
contrasts = [('Tg1','Ctrl'), ('Tg16','Ctrl'), ('Tg16','Tg1'), ('Tg16+PERKi','Tg16')]
fraction_rows = []
fraction_summary = []
native_target = []
for i,c in enumerate(cols):
    native_target.append({**meta[c], 'Pmp22_raw_count': float(mat[ti,i])})
table('fraction-target-native-cells.tsv', native_target)
for method, sf in norm.items():
    # Pseudocount belongs to the native count scale before sample-size normalization.
    logs = np.log2(mat + 0.5)-np.log2(sf[None,:])
    loading = {cond: np.column_stack([logs[:, pairs[(cond,str(r))]['H']]-logs[:, pairs[(cond,str(r))]['In']] for r in range(1,5)]) for cond in conditions}
    for treat, control in contrasts:
        all_ix = [v for (cond,r), pair in pairs.items() if cond in (treat,control) for v in pair.values()]
        eligible = (mat[:,all_ix] >= 10).all(axis=1)
        effects = {}
        for a in assays:
            tx = [pairs[(treat,str(r))][a] for r in range(1,5)]
            bx = [pairs[(control,str(r))][a] for r in range(1,5)]
            effects[a] = logs[:,tx].mean(axis=1)-logs[:,bx].mean(axis=1)
        interaction = loading[treat].mean(axis=1)-loading[control].mean(axis=1)
        assert np.allclose(interaction, effects['H']-effects['In'], atol=1e-12)
        bg = eligible & not_target
        bgmedian = float(np.median(interaction[bg]))
        for i,gene in enumerate(genes):
            row = {'normalization': method, 'contrast': treat+'/'+control, 'gene': gene,
                   'eligible_min10_all_contrast_libraries': bool(eligible[i]),
                   'cytosolic_log2_change': float(effects['In'][i]), 'polysome_log2_change': float(effects['H'][i]),
                   'relative_loading_interaction_log2': float(interaction[i]),
                   'background_centered_interaction_log2': float(interaction[i]-bgmedian),
                   'in_control_panel': gene in PANEL}
            fraction_rows.append(row)
            if gene == 'Pmp22':
                tvals = loading[treat][i]
                bvals = loading[control][i]
                deletions = [float(np.delete(tvals,t).mean()-np.delete(bvals,b).mean()) for t in range(4) for b in range(4)]
                fraction_summary.append({**row, 'control_loading': bvals.tolist(), 'treated_loading': tvals.tolist(),
                                         'delete_one_per_group_range': [min(deletions), max(deletions)],
                                         'background_n': int(bg.sum()), 'background_median': bgmedian,
                                         'background_percentile': float(100*np.mean(interaction[bg] <= interaction[i])),
                                         'p_value': None, 'uncertainty_limit': 'Deletion range is descriptive, not a confidence interval. Four replicate labels are not established donor/culture independence.'})
table('fraction-interactions-all-genes.tsv', fraction_rows)

# Source-defined log10 TE: preserve all native rows, collapse only exact gene/vector repeats.
with gzip.open(PUB/'GSE103667_TE.norm.txt.gz','rt') as f:
    native = list(csv.DictReader(f, delimiter='\t'))
by_gene = defaultdict(list)
for row in native:
    vec = tuple(float(row[c]) for c in ['TE.DMSO1','TE.THAP1','TE.DMSO2','TE.THAP2'])
    assert all(math.isfinite(x) for x in vec)
    by_gene[row['name']].append((row,vec))
te_rows = []
te_target = []
ambiguous = []
for gene, rr in by_gene.items():
    if gene == 'Pmp22':
        te_target = [r for r,v in rr]
    unique = {v for r,v in rr}
    if len(unique) != 1:
        ambiguous.append({'gene': gene, 'distinct_vectors': len(unique), 'native_rows': len(rr)})
        continue
    vec = next(iter(unique))
    d = [vec[1]-vec[0], vec[3]-vec[2]]
    row = {'gene': gene, 'refSeqIDs': '|'.join(r['refSeqID'] for r,v in rr), 'native_rows': len(rr),
           'TE_DMSO1': vec[0], 'TE_THAP1': vec[1], 'TE_DMSO2': vec[2], 'TE_THAP2': vec[3],
           'delta_source_scale_rep1': d[0], 'delta_source_scale_rep2': d[1],
           'delta_log2_if_paper_log10_rep1': d[0]*math.log2(10),
           'delta_log2_if_paper_log10_rep2': d[1]*math.log2(10),
           'in_control_panel': gene in PANEL}
    te_rows.append(row)
assert te_target
bg = np.array([[r['delta_source_scale_rep1'],r['delta_source_scale_rep2']] for r in te_rows if r['gene'] != 'Pmp22'])
target = []
for native_row in te_target:
    vec = [float(native_row[c]) for c in ['TE.DMSO1','TE.THAP1','TE.DMSO2','TE.THAP2']]
    d = [vec[1]-vec[0], vec[3]-vec[2]]
    target.append({**native_row,
                   'delta_source_scale_rep1':d[0], 'delta_source_scale_rep2':d[1],
                   'conditional_log2_if_export_linear_rep1':math.log2(vec[1]/vec[0]) if min(vec[:2])>0 else None,
                   'conditional_log2_if_export_linear_rep2':math.log2(vec[3]/vec[2]) if min(vec[2:])>0 else None,
                   'conditional_log2_if_export_log10_rep1':d[0]*math.log2(10),
                   'conditional_log2_if_export_log10_rep2':d[1]*math.log2(10),
                   'background_centered_source_rep1':d[0]-float(np.median(bg[:,0])),
                   'background_centered_source_rep2':d[1]-float(np.median(bg[:,1]))})
table('TE-target-native-cells.tsv', target)
te_summary = {'native_rows': len(native), 'unique_gene_labels': len(by_gene), 'unambiguous_genes': len(te_rows),
              'ambiguous_genes_excluded': ambiguous, 'target_native_rows': te_target, 'target': target,
              'background_median_source_scale': np.median(bg,axis=0).tolist(),

              'negative_native_TE_cells': sum(float(r[c]) < 0 for r in native for c in ['TE.DMSO1','TE.THAP1','TE.DMSO2','TE.THAP2']),
              'assay_pairing': 'Primary PMC6359928 P58 split supernatant; condition-matched rep labels, culture independence not established',
              'scale': 'Primary P61 states log10 but GEO TE.norm does not state whether this export has been transformed. Both transformations retained conditionally, neither promoted to an identified fold change.',
              'target_aggregation': 'All Pmp22 RefSeq rows retained, including multiple distinct vectors; not averaged as biological replicates. Unambiguous-gene background excludes multi-vector genes.',
              'filter_conflict': 'GEO: RNA counts >=10; paper: >=50 any sequencing reads. Native table lacks constituent counts to check target floor.',
              'global_calibration': 'Total sequenced reads is not an external per-cell RPF spike-in; granule RNA spike-ins do not calibrate this separate RPF assay.',
              'p_value': None}
table('TE-gene-audit.tsv', te_rows)

# Immutable input/HTTP provenance and explicit finite-output checks.
source_rows = []
for p in sorted(PUB.glob('*.receipt.json')):
    r = json.loads(p.read_text())
    body = PUB/r['name']
    if body.exists():
        assert hashlib.sha256(body.read_bytes()).hexdigest() == r['sha256']
    r['scientific_content_usable'] = r.get('success',False) and r['name'] not in ['PMC5730339.html','PMC6359928.html']
    if r['name'] in ['PMC5730339.html','PMC6359928.html']:
        r['content_failure'] = 'HTTP 200 is a reCAPTCHA challenge, not article content'
    source_rows.append(r)
dump('source-locators.json', source_rows)
summary = {'question': 'q_4280e55151994ef8', 'retrospective': True, 'sample_labels': len(samples),
           'sample_counts_by_series': {s: sum(r['series']==s for r in samples) for s in sorted({r['series'] for r in samples})},
           'footprint': foot_summary,
           'fraction': {'native_gene_rows': len(genes), 'target_min_count_all_samples': float(mat[ti].min()),
                        'normalization_feature_counts': {'joint':joint_n, **norm_features}, 'contrasts':fraction_summary},
           'TE': te_summary,
           'inference': 'Endpoint-specific blocker: no calibrated paired RNA/RPF plus target nascent synthesis across the opposed GSE118660 contexts. Relative fraction/TE calculations are retrospective diagnostics, not absolute-synthesis tests or independent biological replication.'}
dump('stress-audit-summary.json', summary)
validation = {'status':'passed', 'sample_map_matches_all_count_columns': True, 'fraction_pairs':len(pairs),
              'finite_inputs':True, 'expected_counts_not_declared_raw_integers':True,
              'interaction_algebra_verified':True, 'source_hashes_verified':True,
              'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('*.tsv'))},
              'no_raw_processing':True, 'no_inherited_code_executed':True}
dump('analysis-validation.json', validation)
print(json.dumps({'sample_labels':len(samples), 'fraction_pairs':len(pairs), 'footprint_target':foot_summary,
                  'fraction_primary':[r for r in fraction_summary if r['normalization']=='assay_separate_median_ratio'],
                  'TE_target':target, 'TE_background':te_summary['background_median_source_scale']}, indent=2, allow_nan=False))
