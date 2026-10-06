"""Locked processed-RNA contrasts; preserve feature universes, statuses and samples."""
import hashlib
import itertools
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OUT = Q / 'outputs'
MANIFEST = json.loads((Q / 'inputs/acquisition/manifest.json').read_text())
PRED = Q / 'outputs/predictions/mechanical-transfer-r001.json'
assert hashlib.sha256(PRED.read_bytes()).hexdigest() == '5239371537f3699d2e6a2b0bdd52e7605ddf2c9e11a822b8ada8ed436701f216'
PANEL = json.loads((Q / 'outputs/prediction-draft.json').read_text())['fixed_panel']
MYELIN = ['MPZ', 'MBP', 'MAG', 'PRX', 'PLP1', 'CNP', 'MAL']
TECH = {'__no_feature', '__ambiguous', '__too_low_aQual', '__not_aligned', '__alignment_not_unique', 'no_feature', 'ambiguous', 'too_low_aQual', 'not_aligned', 'alignment_not_unique'}
QC, SAMPLES, MEASUREMENTS, EFFECTS, COVERAGE = {}, [], [], [], []
ALL_EFFECTS, INTERACTIONS = [], []
MATRICES = {}


def read_native(item):
    path = W / item['path']
    with path.open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == item['blob']
    return path


def soft_samples(path):
    out, current = {}, None
    with path.open() as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('^SAMPLE = '):
                current = line.split(' = ', 1)[1]
                out[current] = {}
            elif line.startswith('^'):
                current = None
            elif current and line.startswith('!Sample_') and ' = ' in line:
                k, v = line.split(' = ', 1)
                out[current].setdefault(k.removeprefix('!Sample_'), []).append(v)
    return out


def setup(series):
    items = [x for x in MANIFEST if x['series'] == series]
    if series == 'GSE79115':
        meta = soft_samples(Q.parent / 'q_e835197734394f30/inputs/primary/GSE79115-samples.soft')
    else:
        meta = soft_samples(Q / f'inputs/primary/{series}-family.soft')
    vals, ann, statuses, samples = {}, {}, {}, {}
    sources = {}
    if series == 'GSE292211':
        assert len(items) == 1
        item = items[0]
        df = pd.read_csv(read_native(item), compression='gzip', sep='\t', dtype=str, keep_default_na=False)
        assert df['GeneID'].is_unique
        df = df.set_index('GeneID')
        mapping = {m['title'][0].split('__')[0]: gsm for gsm, m in meta.items()}
        for c in df.columns.drop('GeneSymbol'):
            gsm = mapping[c]
            vals[gsm] = df[c].astype(float)
            ann[gsm] = df['GeneSymbol']
            statuses[gsm] = pd.Series('measured_count', index=df.index)
            sources[gsm] = item['blob']
            group = 'control' if 'no_comp' in c else ('compression4h' if '4h' in c else 'pulse5min_recovery235min')
            samples[gsm] = {'group': group, 'native_column': c}
    else:
        for item in items:
            gsm = re.search(r'GSM\d+', item['name']).group()
            if series == 'GSE79115':
                df = pd.read_csv(read_native(item), compression='gzip', sep='\t', header=None, names=['feature', 'value'], dtype=str, keep_default_na=False).set_index('feature')
                vals[gsm] = df['value'].astype(float)
                ann[gsm] = pd.Series(df.index, index=df.index)
                statuses[gsm] = pd.Series('measured_count', index=df.index)
                group = 'mutant' if 'DBL-cKO' in meta[gsm]['title'][0] else 'control'
            else:
                df = pd.read_csv(read_native(item), compression='gzip', sep='\t', dtype=str, keep_default_na=False)
                # Native tracking IDs can repeat across distinct loci; never sum or select them.
                df['feature_id'] = df['tracking_id'] + '|' + df['locus']
                assert df['feature_id'].is_unique, (series, gsm, 'duplicate ID+locus')
                df = df.set_index('feature_id')
                vals[gsm] = df['FPKM'].astype(float)
                ann[gsm] = df['gene_short_name']
                statuses[gsm] = df['FPKM_status']
                if series == 'GSE94990':
                    title = meta[gsm]['title'][0]
                    group = 'control' if 'Ctr-TazYap' in title else ('partial' if 'cKOTaz-HetYap' in title else 'double')
                    assert ('dcKO' in title) or group != 'double'
                else:
                    # Exact deposit titles, also checked against source filenames.
                    title = meta[gsm]['title'][0]
                    group = item['name'].split('_', 1)[1].rsplit('_Rep', 1)[0]
                    source_prefix = {'WT': 'WT', 'RAP2KO': 'RAP2A/B/C-tKO', 'LATS1_2dKO': 'LATS1/2-dKO', 'Y_TdKO': 'YAP/TAZ-dKO'}
                    g, stiffness = group.rsplit('_', 1)
                    assert title.rsplit('_Rep', 1)[0] == source_prefix[g]+'_'+stiffness, (title, group)
            assert df.index.is_unique
            sources[gsm] = item['blob']
            samples[gsm] = {'group': group, 'native_column': 'value' if series == 'GSE79115' else 'FPKM'}
    raw = pd.DataFrame(vals).sort_index().sort_index(axis=1)
    status = pd.DataFrame(statuses).reindex_like(raw)
    annotations = pd.DataFrame(ann).reindex_like(raw)
    differing = annotations.nunique(axis=1, dropna=True) > 1
    assert not differing.any(), (series, 'conflicting native gene annotations', annotations[differing].to_dict())
    symbols = annotations.bfill(axis=1).iloc[:, 0]
    assert np.isfinite(raw.to_numpy()[~raw.isna().to_numpy()]).all()
    assert (raw.fillna(0) >= 0).all().all()
    counts = series in ['GSE79115', 'GSE292211']
    if counts:
        assert not raw.isna().any().any(), (series, 'missing count features')
        assert np.equal(raw, np.floor(raw)).all().all()
    tech = raw.index.to_series().isin(TECH)
    counters = raw.loc[tech].to_dict(orient='index')
    raw, symbols, status = raw.loc[~tech], symbols.loc[~tech], status.loc[~tech]
    raw.index.name = 'feature_id'
    raw.to_csv(OUT / f'{series}-native-matrix.tsv.gz', sep='\t', compression={'method': 'gzip', 'mtime': 0})
    status.index.name = 'feature_id'
    status.to_csv(OUT / f'{series}-status-matrix.tsv.gz', sep='\t', compression={'method': 'gzip', 'mtime': 0})
    symbols.rename('native_symbol').to_csv(OUT / f'{series}-annotations.tsv', sep='\t')
    valid = status.eq('measured_count') if counts else status.eq('OK')
    if counts:
        positive = (raw > 0).all(axis=1)
        assert positive.sum() > 1000
        gmean = np.exp(np.log(raw.loc[positive]).mean(axis=1))
        sf = raw.loc[positive].div(gmean, axis=0).median()
        sf = sf / np.exp(np.log(sf).mean())
        primary = raw / sf
        cpm = raw.div(raw.sum(), axis=1) * 1e6
        baseline = cpm
        variants = {'primary': primary, 'CPM': cpm}
    else:
        positive, sf = None, pd.Series(1.0, index=raw.columns)
        primary = raw.where(valid)
        baseline = primary
        variants = {'primary': primary}
    upper = symbols.str.upper()
    panelmap = {}
    for gene in PANEL:
        ids = list(symbols.index[upper.eq(gene)])
        COVERAGE.append({'series': series, 'requested': gene, 'feature_ids': ';'.join(ids), 'n_matches': len(ids), 'status': 'unique' if len(ids) == 1 else ('missing' if not ids else 'ambiguous')})
        if len(ids) == 1:
            panelmap[gene] = ids[0]
    for gsm in raw.columns:
        m = meta[gsm]
        samples[gsm].update({'series': series, 'sample': gsm, 'title': m['title'][0], 'organism': m['organism_ch1'][0], 'characteristics': ' | '.join(m.get('characteristics_ch1', [])), 'source_blob': sources[gsm], 'size_factor': float(sf[gsm]), 'sum_gene_values': float(raw[gsm].sum())})
        SAMPLES.append(samples[gsm])
        for gene, fid in panelmap.items():
            MEASUREMENTS.append({'series': series, 'sample': gsm, 'group': samples[gsm]['group'], 'requested': gene, 'native_symbol': symbols[fid], 'feature_id': fid, 'native': raw.at[fid, gsm], 'status': status.at[fid, gsm], 'normalized': primary.at[fid, gsm], 'baseline_unit_value': baseline.at[fid, gsm], 'source_blob': sources[gsm]})
    QC[series] = {'n_features': len(raw), 'n_samples': len(raw.columns), 'n_native_source_files': len(items), 'counts': counts, 'status_counts': status.stack().value_counts().to_dict(), 'technical_counters': counters, 'all_positive_normalization_features': int(positive.sum()) if counts else None, 'missing_values': int(raw.isna().sum().sum()), 'units': 'HTSeq integer counts; median-ratio normalized count / CPM sensitivity' if counts else 'source FPKM; no re-normalization', 'panel_matches': len(panelmap)}
    MATRICES[series] = {'raw': raw, 'primary': primary, 'symbols': symbols, 'valid': valid, 'baseline': baseline, 'variants': variants, 'panel': panelmap, 'samples': samples}
    print(series, QC[series])


def summarize(x, y):
    """Treatment minus control; conditional unpaired library-level uncertainty."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    assert len(x) >= 2 and len(y) >= 2 and np.isfinite(np.r_[x, y]).all()
    delta = float(x.mean() - y.mean())
    vx, vy = x.var(ddof=1) / len(x), y.var(ddof=1) / len(y)
    variance = vx + vy
    if variance > 0:
        df = variance**2 / (vx**2 / (len(x) - 1) + vy**2 / (len(y) - 1))
        half = float(stats.t.ppf(.975, df) * np.sqrt(variance))
        p = float(2 * stats.t.sf(abs(delta) / np.sqrt(variance), df))
        ci = [delta - half, delta + half]
    else:
        df, p, ci = None, None, [None, None]
    z = np.r_[x, y]
    null = []
    for ids in itertools.combinations(range(len(z)), len(x)):
        mask = np.zeros(len(z), dtype=bool)
        mask[list(ids)] = True
        null.append(z[mask].mean() - z[~mask].mean())
    exact = float(np.mean(np.abs(null) >= abs(delta) - 1e-12))
    loo = [np.delete(x, i).mean() - y.mean() for i in range(len(x))] + [x.mean() - np.delete(y, i).mean() for i in range(len(y))]
    return {'effect_log2': delta, 'ci95_low': ci[0], 'ci95_high': ci[1], 'welch_p': p, 'welch_df': float(df) if df else None, 'permutation_two_sided_p': exact, 'n_permutations': len(null), 'loo_min': float(min(loo)), 'loo_max': float(max(loo)), 'n_treated': len(x), 'n_control': len(y)}


def contrast(series, name, treatment, control):
    m = MATRICES[series]
    a = [s for s in m['raw'].columns if m['samples'][s]['group'] == treatment]
    b = [s for s in m['raw'].columns if m['samples'][s]['group'] == control]
    assert min(len(a), len(b)) >= 2, (name, a, b, m['samples'])
    full = np.log2(m['primary'] + .5)
    effect = full[a].mean(axis=1, skipna=False) - full[b].mean(axis=1, skipna=False)
    whole = pd.DataFrame({'series': series, 'contrast': name, 'native_symbol': m['symbols'], 'effect_log2': effect, 'mean_control': m['primary'][b].mean(axis=1, skipna=False), 'mean_treated': m['primary'][a].mean(axis=1, skipna=False), 'baseline_control': m['baseline'][b].mean(axis=1, skipna=False), 'all_status_valid': m['valid'][a+b].all(axis=1)})
    whole.index.name = 'feature_id'
    ALL_EFFECTS.append(whole.reset_index())
    for variant, data in m['variants'].items():
        for pseudocount in [.5, .1, 1.0]:
            logs = np.log2(data + pseudocount)
            scores, ids = {}, {}
            for g, fid in m['panel'].items():
                scores[g] = logs.loc[fid]
                ids[g] = [fid]
            if all(g in scores for g in MYELIN):
                scores['myelin7'] = pd.DataFrame({g: scores[g] for g in MYELIN}).mean(axis=1, skipna=False)
                ids['myelin7'] = [m['panel'][g] for g in MYELIN]
            for comp in ['EGR2', 'SOX10', 'myelin7']:
                if comp in scores and 'PMP22' in scores:
                    scores['PMP22_minus_' + comp] = scores['PMP22'] - scores[comp]
                    ids['PMP22_minus_' + comp] = ids['PMP22'] + ids[comp]
            for endpoint, score in scores.items():
                fid = ids[endpoint]
                baseline_ok = bool((m['baseline'].loc[fid, b].mean(axis=1, skipna=False) >= 1).all())
                status_ok = bool(m['valid'].loc[fid, a+b].all().all())
                row = {'series': series, 'contrast': name, 'treatment': treatment, 'control': control, 'endpoint': endpoint, 'variant': variant, 'pseudocount': pseudocount, 'baseline_eligible': baseline_ok, 'statuses_valid': status_ok, 'source_features': ';'.join(fid), 'treatment_samples': ';'.join(a), 'control_samples': ';'.join(b), 'inference_scope': 'conditional_on_exchangeable_independent_libraries_not_donors' if min(len(a), len(b)) >= 3 else 'descriptive_n2_no_population_claim'}
                if np.isfinite(score[a+b]).all() and status_ok:
                    row.update(summarize(score[a], score[b]))
                    row.update(mean_control_score=float(score[b].mean()), mean_treated_score=float(score[a].mean()))
                    if endpoint in m['panel']:
                        f = m['panel'][endpoint]
                        row['mean_control_native'] = float(m['raw'].loc[f, b].mean())
                        row['mean_treated_native'] = float(m['raw'].loc[f, a].mean())
                        row['log2_ratio_arithmetic_means'] = float(np.log2((data.loc[f, a].mean()+pseudocount)/(data.loc[f, b].mean()+pseudocount)))
                EFFECTS.append(row)
    print(name, 'PMP22', effect.get(m['panel'].get('PMP22')), 'samples', a, b)


for series in ['GSE79115', 'GSE94990', 'GSE98547', 'GSE292211']:
    setup(series)

CONTRASTS = [
    ('GSE79115', 'P3_partial_loss_vs_control', 'mutant', 'control'),
    ('GSE94990', 'P5_partial_loss_vs_control', 'partial', 'control'),
    ('GSE94990', 'P5_double_loss_vs_control', 'double', 'control'),
    ('GSE292211', 'compression4h_vs_uncompressed', 'compression4h', 'control'),
    ('GSE292211', 'pulse_recovery_vs_uncompressed', 'pulse5min_recovery235min', 'control'),
]
for g in ['WT', 'RAP2KO', 'LATS1_2dKO', 'Y_TdKO']:
    CONTRASTS.append(('GSE98547', g+'_40_minus_1kPa', g+'_40kPa', g+'_1kPa'))
for g in ['RAP2KO', 'LATS1_2dKO', 'Y_TdKO']:
    for k in ['1kPa', '40kPa']:
        CONTRASTS.append(('GSE98547', g+'_minus_WT_'+k, g+'_'+k, 'WT_'+k))
for args in CONTRASTS:
    contrast(*args)

# Four independent groups; log-scale difference-in-differences, not molecular mediation.
m = MATRICES['GSE98547']
for genotype in ['RAP2KO', 'LATS1_2dKO', 'Y_TdKO']:
    groups = [genotype+'_40kPa', genotype+'_1kPa', 'WT_40kPa', 'WT_1kPa']
    for endpoint, fid in m['panel'].items():
        for pc in [.5, .1, 1.0]:
            log = np.log2(m['primary'].loc[fid] + pc)
            arrays = [log[[s for s in log.index if m['samples'][s]['group'] == g]].to_numpy() for g in groups]
            if not all(np.isfinite(x).all() for x in arrays):
                continue
            signs = np.array([1, -1, -1, 1])
            effect = float(sum(s*x.mean() for s, x in zip(signs, arrays, strict=True)))
            v = np.array([x.var(ddof=1)/len(x) for x in arrays])
            if v.sum() > 0:
                df = float(v.sum()**2 / sum(vv**2/(len(x)-1) for vv, x in zip(v, arrays, strict=True)))
                half = float(stats.t.ppf(.975, df)*np.sqrt(v.sum()))
                p = float(2*stats.t.sf(abs(effect)/np.sqrt(v.sum()),df))
            else:
                half, p = np.nan, np.nan
            INTERACTIONS.append({'genotype': genotype, 'endpoint': endpoint, 'pseudocount': pc, 'interaction_KO_minus_WT_log2': effect, 'ci95_low': effect-half, 'ci95_high': effect+half, 'welch_p': p, 'source_feature': fid, 'native_group_means': json.dumps({g:float(m['raw'].loc[fid, [s for s in log.index if m['samples'][s]['group'] == g]].mean()) for g in groups}), 'all_group_baselines_ge1': bool(all(m['raw'].loc[fid, [s for s in log.index if m['samples'][s]['group'] == g]].mean()>=1 for g in groups))})

pd.DataFrame(SAMPLES).to_csv(OUT/'sample-design.tsv', sep='\t', index=False)
pd.DataFrame(COVERAGE).to_csv(OUT/'panel-coverage.tsv', sep='\t', index=False)
pd.DataFrame(MEASUREMENTS).to_csv(OUT/'panel-measurements.tsv', sep='\t', index=False)
pd.DataFrame(EFFECTS).to_csv(OUT/'executed-contrasts.tsv', sep='\t', index=False)
pd.concat(ALL_EFFECTS, ignore_index=True).to_csv(OUT/'full-feature-contrasts.tsv.gz', sep='\t', index=False, compression={'method':'gzip','mtime':0})
pd.DataFrame(INTERACTIONS).to_csv(OUT/'genotype-stiffness-interactions.tsv', sep='\t', index=False)
(OUT/'measurement-qc.json').write_text(json.dumps(QC, indent=2, allow_nan=False)+'\n')
print('COMPLETE', len(MANIFEST), 'native files;', len(SAMPLES), 'libraries;', len(CONTRASTS), 'contrasts')
