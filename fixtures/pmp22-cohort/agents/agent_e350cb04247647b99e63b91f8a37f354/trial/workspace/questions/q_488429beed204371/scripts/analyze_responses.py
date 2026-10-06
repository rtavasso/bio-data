"""Descriptive, source-preserving analysis of selected GSE139321 RNA start signals.

No count model, donor inference, treatment pairing or cAMP-by-SOX10 factorial.
All writes are question-local; no downloaded or inherited code is executed.
"""
import csv
import hashlib
import json
import math
import os
import statistics as st

from itertools import combinations, product
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
OUT.mkdir(exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(Q / 'mpl-cache'))
import matplotlib  # noqa: E402 -- configure a question-local cache before import
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402 -- set noninteractive backend first

SPEC = json.loads((Q / 'analysis-spec.json').read_text())
INPUTS = json.loads((Q / 'sources/immutable-inputs.json').read_text())
NATIVE = Q / INPUTS['native']['path']
assert hashlib.sha256(NATIVE.read_bytes()).hexdigest() == SPEC['native_sha256']


def write_tsv(name, rows):
    assert rows, name
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter='\t', restval='NA')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: 'NA' if v is None else v for k, v in row.items()})


def write_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, allow_nan=False))


def mean(xs):
    return st.mean(xs) if xs and all(x is not None for x in xs) else None


def logratio(x, y):
    return math.log2(x / y) if x > 0 and y > 0 else None


def difference(x, y):
    return x - y if x is not None and y is not None else None


def stats(xs):
    good = [x for x in xs if x is not None]
    result = {'n': len(xs), 'n_defined': len(good)}
    result.update({k: None for k in ['mean', 'sd', 'cv', 'min', 'max', 'median']})
    if len(good) == len(xs) and good:
        m = mean(good)
        sd = st.stdev(good) if len(good) > 1 else None
        result.update(mean=m, sd=sd, cv=sd / m if sd is not None and m > 0 else None,
                      min=min(good), max=max(good), median=st.median(good))
    return result


def interval(xs):
    good = [v for v in xs if v is not None]
    return [min(good), max(good)] if good else [None, None]


with NATIVE.open() as f:
    reader = csv.DictReader(f, delimiter='\t')
    header = reader.fieldnames
    native_rows = [dict(row, native_line=i) for i, row in enumerate(reader, 2)]
assert len(native_rows) == 4993
assert len({r['TSS id'] for r in native_rows}) == len(native_rows)
RPM_COLUMNS = [c for c in header if c.endswith(' RPM')]
assert len(RPM_COLUMNS) == 14
raw_by_id = {r['TSS id']: r for r in native_rows}
values = {}
for row in native_rows:
    values[row['TSS id']] = {c: float(row[c]) for c in RPM_COLUMNS}
    assert all(math.isfinite(x) and x >= 0 for x in values[row['TSS id']].values())
pmp = [r for r in native_rows if r['Gene Symbol'] == 'Pmp22']
assert len(pmp) == 22
assert {r['TSS Chr'] for r in pmp} == {'chr10'}
assert {r['TSS Strand'] for r in pmp} == {'+'}
for cid, loc in {'5439': (49316968, 49317054, 817), '5446': (49319494, 49319573, 824)}.items():
    row = raw_by_id[cid]
    assert (int(row['TSS Start']), int(row['TSS End']), row['native_line']) == loc

# Exact title/header mapping is explicit; native identifiers remain unchanged.
header_map = {
    'GSM4138082': 'Sciatic Nerve 1 RPM', 'GSM4138083': 'Sciatic Nerve 2 RPM',
    'GSM4138084': 'Primary Schwann Cell Control 1 RPM', 'GSM4138085': 'Primary Schwann Cell Control 2 RPM',
    'GSM4138086': 'Primary Schwann Cell Control 3 RPM', 'GSM4138087': 'Primary Schwann Cell cAMP 1 RPM',
    'GSM4138088': 'Primary Schwann Cell cAMP 2 RPM', 'GSM4138089': 'Primary Schwann Cell cAMP 3 RPM',
    'GSM4138090': 'S16 Parental 1 RPM', 'GSM4138091': 'S16 Parental 2 RPM',
    'GSM4138092': 'S16 delSOX10 1-1 RPM', 'GSM4138093': 'S16 delSOX10 1-2 RPM',
    'GSM4138094': 'S16 delSOX10 2-1 RPM', 'GSM4138095': 'S16 delSOX10 2-2 RPM',
}
with (Q / INPUTS['samples']['path']).open() as f:
    source_samples = list(csv.DictReader(f, delimiter='\t'))
assert len(source_samples) == 14
samples = []
for old in source_samples:
    c = header_map[old['accession']]
    group = old['group']
    native_meta = json.loads(old['native_fields'])
    assert native_meta['Sample_geo_accession'] == [old['accession']]
    assert native_meta['Sample_title'] == [old['title']]
    family = c.split('delSOX10 ')[1].split('-')[0] if group == 'S16_SOX10_KO' else None
    samples.append({'accession': old['accession'], 'native_column': c, 'GEO_title': old['title'],
                    'condition': group, 'biological_unit': old['unit'], 'time': old['time'],
                    'dose': '250 uM CPT-cAMP' if group == 'primary_cAMP' else 'vehicle' if group == 'primary_control' else None,
                    'source': 'Kerafast EMI010 primary rat Schwann cells' if group.startswith('primary') else 'S16 ATCC CRL-2941 rat cell line' if group.startswith('S16') else 'adult rat sciatic nerve',
                    'platform': 'NovaSeq' if group.startswith('primary') else 'HiSeq 4000',
                    'assay': 'Tn5Prime from 5 ng total RNA', 'units': 'source RPM', 'assembly': 'rn5',
                    'donor_id': None, 'treatment_pair_id': None, 'within_library_features_paired': True,
                    'clone_label_family': family,
                    'guide_membership_status': 'label-inferred family; paper confirms two guides, no explicit guide-to-clone table in audited main-text metadata' if family else None,
                    'design_locator': 'PMC7430845 Methods Par50, Par51, Par54; inherited GEO native fields',
                    'replication_limit': 'Independent culture populations, donors/lots unestablished' if group.startswith('primary') else 'Shared parental line; two parental RNA samples, four edited clones; no independently cloned parental controls' if group.startswith('S16') else 'Two independent nerves; animal IDs and sex not established'})
assert {s['native_column'] for s in samples} == set(RPM_COLUMNS)
by_col = {s['native_column']: s for s in samples}
groups = {g: [s['native_column'] for s in samples if s['condition'] == g] for g in sorted({s['condition'] for s in samples})}
contrasts = {'cAMP_vs_vehicle': (groups['primary_control'], groups['primary_cAMP']),
             'SOX10_KO_vs_parental': (groups['S16_parental'], groups['S16_SOX10_KO'])}

# Coordinates only define sensitivity membership. No transcript mapping extension.
def midpoint(row):
    return (int(row['TSS Start']) + int(row['TSS End'])) / 2

sets = {'focal': {p: [cid] for p, cid in SPEC['focal'].items()}}
for radius in SPEC['positional_midpoint_radii']:
    sets[f'midpoint_{radius}'] = {p: [r['TSS id'] for r in pmp if abs(midpoint(r) - midpoint(raw_by_id[cid])) <= radius] for p, cid in SPEC['focal'].items()}
for pairsets in sets.values():
    assert not (set(pairsets['P1']) & set(pairsets['P2']))

# Check interval overlap under either base convention conservatively (inclusive tokens).
def overlaps(rows):
    return [(a['TSS id'], b['TSS id']) for a, b in combinations(rows, 2)
            if a['TSS Chr'] == b['TSS Chr'] and a['TSS Strand'] == b['TSS Strand']
            and max(int(a['TSS Start']), int(b['TSS Start'])) <= min(int(a['TSS End']), int(b['TSS End']))]
assert not overlaps(pmp), 'Overlapping Pmp22 source clusters: sums need redesign, not silent double counting'
membership = []
for r in pmp:
    mem = {name: [p for p, ids in pairsets.items() if r['TSS id'] in ids] for name, pairsets in sets.items()}
    membership.append({'cluster_id': r['TSS id'], 'native_line': r['native_line'], 'chromosome': r['TSS Chr'],
                       'start_token': r['TSS Start'], 'end_token': r['TSS End'], 'strand': r['TSS Strand'],
                       'distance_midpoint_P1': midpoint(r) - midpoint(raw_by_id['5439']),
                       'distance_midpoint_P2': midpoint(r) - midpoint(raw_by_id['5446']),
                       **{name: ','.join(roles) or 'outside' for name, roles in mem.items()},
                       'assignment_limit': 'Only focal clusters carry primer-supported P1/P2 association; windows are positional sensitivity sets'})


def aggregate(ids, column):
    return sum(values[cid][column] for cid in ids)


def adjust(v, method, constant):
    return v + constant if method == 'add' else max(v, constant) if method == 'floor' else v


def paired_values(set_name, column, method='none', constant=0):
    a, b = [adjust(aggregate(sets[set_name][p], column), method, constant) for p in ['P1', 'P2']]
    return a, b


def estimate(set_name, control, treated, method='none', constant=0):
    vv = {c: paired_values(set_name, c, method, constant) for c in control + treated}
    cm = [mean([vv[c][i] for c in control]) for i in [0, 1]]
    tm = [mean([vv[c][i] for c in treated]) for i in [0, 1]]
    lfc = [logratio(tm[i], cm[i]) for i in [0, 1]]
    ctrl_lr = mean([logratio(*vv[c]) for c in control])
    trt_lr = mean([logratio(*vv[c]) for c in treated])
    fractions = {c: a / (a+b) if a+b > 0 else None for c, (a,b) in vv.items()}
    return {'set': set_name, 'method': method, 'constant_RPM': constant,
            'control_n_libraries': len(control), 'treated_n_libraries': len(treated),
            'P1_control_mean_RPM': cm[0], 'P1_treated_mean_RPM': tm[0],
            'P2_control_mean_RPM': cm[1], 'P2_treated_mean_RPM': tm[1],
            'P1_RPM_difference': tm[0] - cm[0], 'P2_RPM_difference': tm[1] - cm[1],
            'P1_fold_of_means': tm[0]/cm[0] if cm[0] > 0 else None,
            'P2_fold_of_means': tm[1]/cm[1] if cm[1] > 0 else None,
            'P1_log2_fold_of_means': lfc[0], 'P2_log2_fold_of_means': lfc[1],
            'P1_minus_P2_log2_fold_of_means': difference(*lfc),
            'control_mean_log2_P1_P2': ctrl_lr, 'treated_mean_log2_P1_P2': trt_lr,
            'change_mean_log2_P1_P2': difference(trt_lr, ctrl_lr),
            'control_mean_P1_fraction': mean([fractions[c] for c in control]),
            'treated_mean_P1_fraction': mean([fractions[c] for c in treated]),
            'P1_fraction_pp_change': 100 * (mean([fractions[c] for c in treated]) - mean([fractions[c] for c in control])),
            'interpretation': 'descriptive; no independent-donor CI or interaction p-value'}

per_library = []
condition_rows = []
for set_name in sets:
    for c in RPM_COLUMNS:
        a, b = paired_values(set_name, c)
        total = aggregate([r['TSS id'] for r in pmp], c)
        per_library.append({'set': set_name, 'accession': by_col[c]['accession'], 'native_column': c,
                            'condition': by_col[c]['condition'], 'clone_label_family': by_col[c]['clone_label_family'],
                            'P1_RPM': a, 'P2_RPM': b, 'log2_P1_P2': logratio(a,b),
                            'P1_fraction_focal_or_window_pair': a/(a+b) if a+b else None,
                            'all_22_selected_Pmp22_RPM_sum': total,
                            'P1_fraction_all22': a/total if total else None,
                            'P2_fraction_all22': b/total if total else None,
                            'other_selected_RPM': total-a-b,
                            'fraction_limit': 'Composition of selected start signal, not all Pmp22 transcripts'})
    for group, cols in groups.items():
        for measure in ['P1_RPM', 'P2_RPM', 'log2_P1_P2', 'P1_fraction_focal_or_window_pair']:
            condition_rows.append({'set': set_name, 'condition': group, 'measure': measure,
                                   **stats([r[measure] for r in per_library if r['set'] == set_name and r['native_column'] in cols])})
            if measure == 'log2_P1_P2':
                condition_rows[-1]['cv'] = None  # CV is not meaningful on a log-ratio scale.

contrast_rows, loo_rows, cross_rows, family_rows = [], [], [], []
for contrast, (control, treated) in contrasts.items():
    for set_name in sets:
        for spec in SPEC['low_signal']:
            method, constant = spec['method'], spec['constant']
            result = {'contrast': contrast, **estimate(set_name, control, treated, method, constant)}
            contrast_rows.append(result)
            for omitted in control + treated:
                cc, tt = [c for c in control if c != omitted], [c for c in treated if c != omitted]
                loo_rows.append({'contrast': contrast, 'omitted_library': omitted, **estimate(set_name, cc, tt, method, constant)})
            for c, t in product(control, treated):
                cp, tp = paired_values(set_name, c, method, constant), paired_values(set_name, t, method, constant)
                cross_rows.append({'contrast': contrast, 'set': set_name, 'method': method, 'constant_RPM': constant,
                                   'control_column': c, 'treated_column': t,
                                   'P1_log2_ratio': logratio(tp[0], cp[0]), 'P2_log2_ratio': logratio(tp[1], cp[1]),
                                   'difference_log2_P1_P2': difference(logratio(*tp), logratio(*cp)),
                                   'independence': 'Not independent pairs; shared libraries. Descriptive range only'})
            if contrast == 'SOX10_KO_vs_parental':
                for family in ['1','2']:
                    tt = [c for c in treated if by_col[c]['clone_label_family'] == family]
                    family_rows.append({'clone_label_family': family, 'guide_assignment': 'label-inferred, not separately verified',
                                        **estimate(set_name, control, tt, method, constant)})

# All PMP22 rows individually, including zero versus low positive distinction.
cluster_contrasts = []
for r in pmp:
    for contrast, (control, treated) in contrasts.items():
        cc, tt = [values[r['TSS id']][c] for c in control], [values[r['TSS id']][c] for c in treated]
        cm, tm = mean(cc), mean(tt)
        cluster_contrasts.append({'cluster_id': r['TSS id'], 'native_line': r['native_line'], 'contrast': contrast,
                                  'control_mean_RPM': cm, 'treated_mean_RPM': tm,
                                  'control_sd_RPM': st.stdev(cc), 'treated_sd_RPM': st.stdev(tt),
                                  'control_min': min(cc), 'control_max': max(cc), 'treated_min': min(tt), 'treated_max': max(tt),
                                  'control_zero_libraries': cc.count(0), 'treated_zero_libraries': tt.count(0),
                                  'log2_fold_of_means_no_pseudocount': logratio(tm,cm),
                                  'log2_fold_of_means_add0.1': logratio(tm+0.1,cm+0.1),
                                  'log2_fold_of_means_add1': logratio(tm+1,cm+1),
                                  'source_edgeR_log2FC_token': r['Primary SC cAMP vs Control log2FC' if contrast.startswith('cAMP') else 'S16 delSOX10 vs Parental log2FC'],
                                  'source_edgeR_FDR_token': r['Primary SC cAMP vs Control FDR-corrected P-value' if contrast.startswith('cAMP') else 'S16 delSOX10 vs Parental FDR-corrected P-value'],
                                  'source_statistic_note': 'Copied source output, not fitted here; not a P1-vs-P2 difference test'})

coverage, comparator_libs, comparator_contrasts = [], [], []
allgenes = [('Pmp22', 'target')] + [(g, panel) for panel, genes in SPEC['comparators'].items() for g in genes]
for gene, panel in allgenes:
    rr = [r for r in native_rows if r['Gene Symbol'] == gene]
    ids = [r['TSS id'] for r in rr]
    coverage.append({'gene': gene, 'panel': panel, 'selected_cluster_count': len(ids), 'ids': ','.join(ids),
                     'interval_overlap_pairs': str(overlaps(rr)),
                     'eligibility': 'measured in selected universe' if ids else 'absent from selected table; unmeasured versus selected-out unresolved, NOT zero'})
    if not ids:
        continue
    assert not overlaps(rr), f'Overlapping comparator intervals: {gene}'
    for contrast, (control, treated) in contrasts.items():
        dominant = max(ids, key=lambda i: mean([values[i][c] for c in control]))
        for strategy, members in [('all_selected_clusters_sum', ids), ('control_dominant_cluster', [dominant])]:
            mm = {c: aggregate(members, c) for c in control+treated}
            for c in control+treated:
                comparator_libs.append({'contrast': contrast, 'gene': gene, 'panel': panel, 'strategy': strategy,
                                        'member_ids': ','.join(members), 'accession': by_col[c]['accession'],
                                        'native_column': c, 'condition': by_col[c]['condition'], 'RPM': mm[c]})
            for spec in SPEC['low_signal']:
                cc = [adjust(mm[c], spec['method'], spec['constant']) for c in control]
                tt = [adjust(mm[c], spec['method'], spec['constant']) for c in treated]
                cm, tm = mean(cc), mean(tt)
                comparator_contrasts.append({'contrast': contrast, 'gene': gene, 'panel': panel, 'strategy': strategy,
                                             'member_ids': ','.join(members), 'method': spec['method'], 'constant_RPM': spec['constant'],
                                             'control_mean_RPM': cm, 'treated_mean_RPM': tm, 'RPM_difference': tm-cm,
                                             'control_min_RPM': min(cc), 'treated_min_RPM': min(tt),
                                             'control_sd_RPM': st.stdev(cc), 'treated_sd_RPM': st.stdev(tt),
                                             'log2_fold_of_means': logratio(tm,cm),
                                             'change_mean_log2_RPM': difference(mean([logratio(x,1) for x in tt]), mean([logratio(x,1) for x in cc])),
                                             'selection_limit': 'Selected start clusters, not whole-gene RNA; dominant cluster chosen from contrast controls only'})

quality = []
for c in RPM_COLUMNS:
    vv = [values[r['TSS id']][c] for r in native_rows]
    quality.append({'accession': by_col[c]['accession'], 'native_column': c, 'condition': by_col[c]['condition'],
                    'selected_rows': len(vv), 'finite_nonnegative_rows': sum(math.isfinite(v) and v >= 0 for v in vv),
                    'zeros': vv.count(0), 'positive_below_1_RPM': sum(0 < v < 1 for v in vv),
                    'at_least_1_RPM': sum(v >= 1 for v in vv), 'selected_RPM_sum': sum(vv),
                    'universe_limit': 'Not library totals; cannot reconstruct counts or full-transcriptome normalization'})

primary = [r for r in contrast_rows if r['set'] == 'focal' and r['method'] == 'none']
summary = {'question': Q.name, 'source_sha256': SPEC['native_sha256'], 'source_rows': len(native_rows),
           'Pmp22_rows': len(pmp), 'library_counts': {g:len(v) for g,v in groups.items()}, 'sets': sets,
           'primary_contrasts': primary, 'robustness': {}, 'unsupported': SPEC['prohibited_interpretations']}
for contrast in contrasts:
    crows = [r for r in contrast_rows if r['contrast'] == contrast]
    lr = [r for r in loo_rows if r['contrast'] == contrast and r['set'] == 'focal' and r['method'] == 'none']
    xr = [r for r in cross_rows if r['contrast'] == contrast and r['set'] == 'focal' and r['method'] == 'none']
    summary['robustness'][contrast] = {
        'window_low_signal_specifications_n': len(crows),
        'window_low_signal_mean_logratio_defined_n': sum(r['change_mean_log2_P1_P2'] is not None for r in crows),
        'window_low_signal_mean_logratio_undefined_n': sum(r['change_mean_log2_P1_P2'] is None for r in crows),
        'all_window_low_signal_mean_logratio_range': interval([r['change_mean_log2_P1_P2'] for r in crows]),
        'all_window_low_signal_fold_of_means_difference_range': interval([r['P1_minus_P2_log2_fold_of_means'] for r in crows]),
        'focal_leave_one_mean_logratio_range': interval([r['change_mean_log2_P1_P2'] for r in lr]),
        'focal_leave_one_mean_logratio_defined_n': sum(r['change_mean_log2_P1_P2'] is not None for r in lr),
        'focal_leave_one_total_n': len(lr),
        'all_window_low_signal_leave_one_mean_logratio_range': interval([r['change_mean_log2_P1_P2'] for r in loo_rows if r['contrast'] == contrast]),
        'all_window_low_signal_leave_one_fold_difference_range': interval([r['P1_minus_P2_log2_fold_of_means'] for r in loo_rows if r['contrast'] == contrast]),
        'focal_leave_one_fold_of_means_difference_range': interval([r['P1_minus_P2_log2_fold_of_means'] for r in lr]),
        'focal_cross_library_logratio_difference_range': interval([r['difference_log2_P1_P2'] for r in xr]),
        'focal_cross_library_defined_n': sum(r['difference_log2_P1_P2'] is not None for r in xr),
        'focal_cross_library_total_n': len(xr),
        'focal_cross_library_positive_n': sum(r['difference_log2_P1_P2'] is not None and r['difference_log2_P1_P2'] > 0 for r in xr),
        'focal_cross_library_negative_n': sum(r['difference_log2_P1_P2'] is not None and r['difference_log2_P1_P2'] < 0 for r in xr),
        'range_type': 'Observed or specification sensitivity range; NOT a confidence interval'}
summary['comparator_coverage'] = coverage
summary['focal_clone_family_contrasts'] = [r for r in family_rows if r['set'] == 'focal' and r['method'] == 'none']

outputs = {
    'sample-design.tsv': samples, 'pmp22-native-rows.tsv': pmp, 'cluster-membership.tsv': membership,
    'per-library-start-signals.tsv': per_library, 'condition-variation.tsv': condition_rows,
    'contrasts-and-sensitivity.tsv': contrast_rows, 'leave-one-library.tsv': loo_rows,
    'cross-library-contrasts.tsv': cross_rows, 'clone-family-contrasts.tsv': family_rows,
    'all-pmp22-cluster-contrasts.tsv': cluster_contrasts, 'comparator-coverage.tsv': coverage,
    'comparator-per-library.tsv': comparator_libs, 'comparator-contrasts.tsv': comparator_contrasts,
    'selected-universe-quality.tsv': quality,
}
for name, rows in outputs.items():
    write_tsv(name, rows)
write_json('summary.json', summary)

# Figures show observed libraries, never manufactured confidence intervals.
colors = {'P1': '#1f77b4', 'P2': '#d95f02'}
fig, axs = plt.subplots(2, 2, figsize=(11, 8))
for col, (contrast, (control, treated)) in enumerate(contrasts.items()):
    for pidx, promoter in enumerate(['P1','P2']):
        for x, cs in enumerate([control, treated]):
            ys = [paired_values('focal', c)[pidx] for c in cs]
            xx = [x + (j-(len(cs)-1)/2)*0.035 + (pidx-0.5)*0.18 for j in range(len(cs))]
            axs[0,col].scatter(xx, ys, c=colors[promoter], label=promoter if x == 0 else None)
            axs[0,col].plot([x-0.06+(pidx-0.5)*0.18,x+0.06+(pidx-0.5)*0.18], [mean(ys)]*2, c=colors[promoter])
    axs[0,col].set_yscale('symlog', linthresh=0.1)
    axs[0,col].set_ylabel('Native RPM (symlog); bar = arithmetic mean')
    axs[0,col].legend()
    for x, cs in enumerate([control,treated]):
        ys = [logratio(*paired_values('focal',c)) for c in cs]
        for j,(c,y) in enumerate(zip(cs,ys,strict=True)):
            xx = x+(j-(len(cs)-1)/2)*0.055
            if y is not None:
                axs[1,col].scatter(xx,y,color='black')
                axs[1,col].annotate(c.removesuffix(' RPM').split()[-1],(xx,y),xytext=(5,3),textcoords='offset points',fontsize=7)
        if mean(ys) is not None:
            axs[1,col].plot([x-0.14,x+0.14],[mean(ys)]*2,color='black')
    axs[1,col].set_ylabel('Within-library log2(P1-associated / P2-associated)')
    if col == 0:
        axs[1,col].text(0.02, 0.02, 'Control 1: P1=0; log ratio undefined (not dropped from arithmetic means)',
                       transform=axs[1,col].transAxes, fontsize=7, wrap=True)
    for ax in axs[:,col]:
        ax.set_xticks([0,1], ['Vehicle','cAMP'] if col == 0 else ['Parental','SOX10 KO clones'])
        ax.set_xlim(-0.45,1.5)
        ax.set_title(contrast)
fig.suptitle('GSE139321 focal clusters 5439 and 5446: co-movement and composition\nRNA start signals; library variation is not donor uncertainty')
fig.tight_layout()
fig.savefig(OUT / 'focal-library-responses.png', dpi=180)
fig.savefig(OUT / 'focal-library-responses.svg')
plt.close(fig)

fig, axs = plt.subplots(1,2,figsize=(12,5))
for ax, contrast in zip(axs,contrasts,strict=True):
    for y,set_name in enumerate(sets):
        rr = [r for r in contrast_rows if r['contrast']==contrast and r['set']==set_name]
        ax.scatter([r['change_mean_log2_P1_P2'] for r in rr],[y]*len(rr),s=35,alpha=0.7)
    ax.axvline(0,c='gray',ls='--')
    ax.set_yticks(range(len(sets)), list(sets))
    ax.set_xlabel('Change in mean within-library log2(P1/P2)')
    ax.set_title(contrast)
fig.suptitle('Frozen cluster windows × low-signal handling\nSensitivity specifications, not independent experiments or confidence intervals')
fig.tight_layout()
fig.savefig(OUT / 'robustness-grid.png', dpi=180)
plt.close(fig)

fig, axs = plt.subplots(1,2,figsize=(12,8))
genes = [r['gene'] for r in coverage if r['selected_cluster_count']]
for ax, contrast in zip(axs,contrasts,strict=True):
    for strategy,marker,offset in [('all_selected_clusters_sum','o',-0.12),('control_dominant_cluster','s',0.12)]:
        rr = {r['gene']:r for r in comparator_contrasts if r['contrast']==contrast and r['strategy']==strategy and r['method']=='add' and r['constant_RPM']==0.1}
        ax.scatter([rr[g]['log2_fold_of_means'] for g in genes],[i+offset for i in range(len(genes))],marker=marker,label=strategy,s=28)
    ax.axvline(0,c='gray',ls='--')
    ax.set_yticks(range(len(genes)),genes)
    ax.set_xlabel('log2 ratio of arithmetic means (+0.1 RPM)')
    ax.set_title(contrast)
    ax.legend(fontsize=7)
fig.suptitle('Measured prespecified comparators: selected start-cluster signals\nNo assumed invariant gene; absent panel members reported in coverage table')
fig.tight_layout()
fig.savefig(OUT / 'comparator-responses.png', dpi=180)
plt.close(fig)

write_json('analysis-output-manifest.json', {'files': [{'name': p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(OUT.iterdir()) if p.name in outputs or p.name in ['summary.json','focal-library-responses.png','focal-library-responses.svg','robustness-grid.png','comparator-responses.png']],
                                          'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                          'spec_sha256':hashlib.sha256((Q/'analysis-spec.json').read_bytes()).hexdigest()})
print(json.dumps(summary, indent=2, allow_nan=False))
