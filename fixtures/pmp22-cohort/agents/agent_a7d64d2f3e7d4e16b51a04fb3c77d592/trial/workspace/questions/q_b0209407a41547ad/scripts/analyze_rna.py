"""Exploratory RNA-program contrasts; source-labelled libraries, not causal adjustment."""
import hashlib
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
PLAN = json.loads((Q / 'inputs/analysis-plan.json').read_text())
MODULES = PLAN['modules']


def bh(p):
    p = np.asarray(p, dtype=float)
    result = np.full(p.shape, np.nan)
    good = np.flatnonzero(np.isfinite(p))
    order = good[np.argsort(p[good])]
    vals = p[order] * len(order) / np.arange(1, len(order) + 1)
    result[order] = np.minimum(1, np.minimum.accumulate(vals[::-1])[::-1])
    return result


def effect(values, treatment, permutation=True):
    values = np.asarray(values)
    a, b = values[treatment], values[~treatment]
    delta = float(a.mean() - b.mean())
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = np.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1)) if se else None
    margin = float(stats.t.ppf(.975, df) * se) if se else 0
    p = float(2 * stats.t.sf(abs(delta / se), df)) if se else None
    perm = []
    if permutation:
        for selection in combinations(range(len(values)), len(a)):
            mask = np.zeros(len(values), dtype=bool)
            mask[list(selection)] = True
            perm.append(float(values[mask].mean() - values[~mask].mean()))
    return {'delta_log2': delta, 'ci95_low': delta - margin, 'ci95_high': delta + margin,
            'welch_p': p, 'permutation_p': sum(abs(x) >= abs(delta) - 1e-12 for x in perm) / len(perm) if perm else None,
            'n_treatment': int(treatment.sum()), 'n_control': int((~treatment).sum())}


program_rows, gene_rows, sample_rows, sensitivity_rows, eligibility_rows, qc_rows, maps = [], [], [], [], [], [], []
for label, acc in [('Acly', 'GSE252209'), ('CMT', 'GSE115930')]:
    acquired = json.loads((OUT / f'{label}-acquired.json').read_text())
    receipt = json.loads((OUT / f'{label}-fetch.json').read_text())
    path = Path(acquired['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == receipt['blob']
    native = pd.read_csv(path, sep=',' if label == 'Acly' else '\t', compression='gzip')
    ids = native.gene_id.astype(str)
    symbols = native.gene_name if label == 'Acly' else native.gene_id.str.split('_', n=1).str[1]
    ages = ['5wk'] if label == 'Acly' else ['E21', 'P6', 'P18']
    for age in ages:
        columns = ['AW1', 'AW2', 'AK1', 'AK2', 'AK3'] if label == 'Acly' else [c for c in native.columns if c.startswith(age + '_')]
        treat = np.array([c.startswith('AK') if label == 'Acly' else '_TG_' in c for c in columns])
        key = f'{acc}_{age}'
        counts = native[columns].to_numpy(dtype=float)
        assert np.isfinite(counts).all() and (counts >= 0).all()
        usable = (counts > 0).all(axis=1)
        geo = np.exp(np.log(counts[usable]).mean(axis=1))
        size_factors = np.median(counts[usable] / geo[:, None], axis=0)
        normalized = counts / size_factors
        log = np.log2(normalized + .5)
        cpm_log = np.log2(counts / counts.sum(axis=0) * 1e6 + .01)
        baseline = normalized[:, ~treat].mean(axis=1)
        eligible = baseline >= 10
        mean_delta = log[:, treat].mean(axis=1) - log[:, ~treat].mean(axis=1)
        va = log[:, treat].var(axis=1, ddof=1) / treat.sum()
        vb = log[:, ~treat].var(axis=1, ddof=1) / (~treat).sum()
        se = np.sqrt(va + vb)
        with np.errstate(divide='ignore', invalid='ignore'):
            degrees = (va + vb) ** 2 / (va ** 2 / (treat.sum()-1) + vb ** 2 / ((~treat).sum()-1))
            pvalues = 2 * stats.t.sf(np.abs(mean_delta / se), degrees)
            margins = stats.t.ppf(.975, degrees) * se
        qvalues = bh(np.where(eligible, pvalues, np.nan))
        for i in range(len(native)):
            gene_rows.append({'contrast': key, 'gene_id': ids.iloc[i], 'symbol': symbols.iloc[i],
                              'control_mean_normalized': baseline[i], 'eligible_baseline10': bool(eligible[i]),
                              'delta_log2': mean_delta[i], 'ci95_low': mean_delta[i]-margins[i], 'ci95_high': mean_delta[i]+margins[i],
                              'welch_p': pvalues[i], 'bh_q_eligible_background': qvalues[i]})
        selected, scores = {}, {}
        for module, members in MODULES.items():
            rows = []
            for symbol in members:
                ix = np.flatnonzero((symbols == symbol).to_numpy())
                status = 'missing' if len(ix) == 0 else 'ambiguous_symbol' if len(ix) > 1 else 'below_control_floor' if not eligible[ix[0]] else 'eligible'
                eligibility_rows.append({'contrast': key, 'module': module, 'symbol': symbol, 'status': status,
                                         'source_rows': len(ix), 'control_mean_normalized': baseline[ix[0]] if len(ix) == 1 else None})
                if status == 'eligible':
                    rows.append(ix[0])
            selected[module] = rows
            if rows:
                scores[module] = log[rows].mean(axis=0)
                record = {'contrast': key, 'endpoint': module, 'members_used': len(rows), 'members_requested': len(members),
                          'complete_module': len(rows) == len(members), **effect(scores[module], treat)}
                program_rows.append(record)
                cp = effect(cpm_log[rows].mean(axis=0), treat)
                sensitivity_rows.append({'contrast': key, 'endpoint': module, 'variant': 'CPM_plus_0.01', 'delta_log2': cp['delta_log2']})
        for one, two in PLAN['relative_endpoints']:
            if one in scores and two in scores:
                name = f'{one}_minus_{two}'
                scores[name] = scores[one] - scores[two]
                record = {'contrast': key, 'endpoint': name, 'members_used': len(selected[one])+len(selected[two]),
                          'members_requested': len(MODULES[one])+len(MODULES[two]),
                          'complete_module': len(selected[one]) == len(MODULES[one]) and len(selected[two]) == len(MODULES[two]),
                          **effect(scores[name], treat)}
                program_rows.append(record)
                cscore = cpm_log[selected[one]].mean(axis=0) - cpm_log[selected[two]].mean(axis=0)
                sensitivity_rows.append({'contrast': key, 'endpoint': name, 'variant': 'CPM_plus_0.01', 'delta_log2': effect(cscore, treat)['delta_log2']})
                for component in [one, two]:
                    if len(selected[component]) > 1:
                        for ix in selected[component]:
                            reduced = [i for i in selected[component] if i != ix]
                            replacement = log[reduced].mean(axis=0)
                            altered = replacement - scores[two] if component == one else scores[one] - replacement
                            sensitivity_rows.append({'contrast': key, 'endpoint': name, 'variant': f'omit_gene:{component}:{symbols.iloc[ix]}', 'delta_log2': effect(altered, treat, False)['delta_log2']})
        wanted = sorted(set(PLAN['gene_endpoints'] + sum(MODULES.values(), [])))
        for sym in wanted:
            ix = np.flatnonzero((symbols == sym).to_numpy())
            if len(ix) != 1:
                continue
            idx = ix[0]
            score = log[idx]
            if sym not in scores:
                scores['gene:' + sym] = score
            for j, column in enumerate(columns):
                sample_rows.append({'contrast': key, 'sample': column, 'group': 'perturbed' if treat[j] else 'control',
                                    'endpoint': 'gene:' + sym, 'raw_count': counts[idx,j], 'normalized_count': normalized[idx,j], 'value_log2': score[j]})
        for name, score in scores.items():
            if not name.startswith('gene:'):
                for j, column in enumerate(columns):
                    sample_rows.append({'contrast': key, 'sample': column, 'group': 'perturbed' if treat[j] else 'control',
                                        'endpoint': name, 'raw_count': None, 'normalized_count': None, 'value_log2': score[j]})
            for j, column in enumerate(columns):
                keep = np.arange(len(columns)) != j
                if min(treat[keep].sum(), (~treat[keep]).sum()) >= 1:
                    vals, t = score[keep], treat[keep]
                    sensitivity_rows.append({'contrast': key, 'endpoint': name, 'variant': 'omit_library:' + column,
                                             'delta_log2': float(vals[t].mean()-vals[~t].mean())})
        for j, column in enumerate(columns):
            qc_rows.append({'contrast': key, 'sample': column, 'library_count_sum': counts[:,j].sum(), 'size_factor': size_factors[j],
                            'normalization_genes': int(usable.sum()), 'native_rows': len(native), 'baseline_eligible_rows': int(eligible.sum()),
                            'fractional_count_rows': int(((counts % 1) != 0).any(axis=1).sum())})
            maps.append({'contrast': key, 'accession': acc, 'sample': column, 'group': 'perturbed' if treat[j] else 'control',
                         'species': 'Mus musculus' if label == 'Acly' else 'Rattus norvegicus', 'age': age,
                         'preparation': 'sciatic nerve bulk', 'source_blob': receipt['blob'],
                         'intervention': 'Acly f/f Mpz-cre versus Acly f/f' if label == 'Acly' else 'Pmp22 transgenic versus wild-type',
                         'unit_limit': 'source-labelled biological libraries; individual sex/litter or pooling unresolved'})

programs = pd.DataFrame(program_rows)
programs['bh_q_fixed_endpoint_family'] = bh(programs.welch_p)
programs.to_csv(OUT / 'rna-program-contrasts.tsv', sep='\t', index=False, na_rep='NA')
pd.DataFrame(gene_rows).to_csv(OUT / 'rna-all-gene-contrasts.tsv.gz', sep='\t', index=False, compression='gzip', na_rep='NA')
pd.DataFrame(sample_rows).to_csv(OUT / 'rna-per-sample.tsv', sep='\t', index=False, na_rep='NA')
pd.DataFrame(sensitivity_rows).to_csv(OUT / 'rna-sensitivities.tsv', sep='\t', index=False, na_rep='NA')
pd.DataFrame(eligibility_rows).to_csv(OUT / 'rna-eligibility.tsv', sep='\t', index=False, na_rep='NA')
pd.DataFrame(qc_rows).to_csv(OUT / 'rna-qc.tsv', sep='\t', index=False)
pd.DataFrame(maps).to_csv(OUT / 'source-contrast-map.tsv', sep='\t', index=False)
validation = {'valid': True, 'contrasts': sorted(programs.contrast.unique()), 'program_rows': len(programs),
              'source_matrices': 2, 'all_gene_contrast_rows': len(gene_rows), 'sample_endpoint_rows': len(sample_rows),
              'native_nonnegative_finite': True, 'fractional_counts_preserved': True,
              'ineligible_program_members': [x for x in eligibility_rows if x['status'] != 'eligible'],
              'limits': ['descriptive conditional library-level intervals; not proof of independence', 'RNA is not flux or promoter initiation',
                         'no biological replication claimed', 'module selection prespecified; source headline outcomes exposed']}
(OUT / 'rna-validation.json').write_text(json.dumps(validation, indent=2, allow_nan=False))
print(programs[['contrast','endpoint','delta_log2','ci95_low','ci95_high','permutation_p','complete_module']].to_string(index=False))
print(json.dumps(validation, indent=2))
