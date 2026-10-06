"""Quantify native cargo endpoints without importing inherited scientific code or evaluating workbook formulas."""
import csv
import hashlib
import itertools
import json
import math
import posixpath
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl
from defusedxml import ElementTree as ET
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'inputs/public'
OUT = ROOT / 'outputs'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
used = {}
checks = []
measurements = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, condition):
    checks.append({'check': name, 'passed': bool(condition)})
    assert condition, name


def workbook(name):
    used[name] = sha(P / name)
    return openpyxl.load_workbook(P / name, read_only=True, data_only=False, keep_links=False)


def literal_sheet(name, sheet):
    """Preserve actual OOXML numeric tokens, including misformatted numeric cells."""
    used[name] = sha(P / name)
    with zipfile.ZipFile(P / name) as z:
        w = ET.fromstring(z.read('xl/workbook.xml'))
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        mapping = {r.get('Id'): r.get('Target') for r in rels}
        selected = [s for s in w.findall('s:sheets/s:sheet', NS) if s.get('name') == sheet]
        check(f'{name}:{sheet}:unique', len(selected) == 1)
        rid = selected[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        target = mapping[rid]
        target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        data = ET.fromstring(z.read(target))
        result = {}
        for c in data.findall('.//s:sheetData/s:row/s:c', NS):
            v = c.find('s:v', NS)
            result[c.get('r')] = {'token': None if v is None else v.text, 'type': c.get('t', 'n'), 'style': c.get('s'), 'formula': c.find('s:f', NS) is not None}
    return result


def numbers(cells, addresses, file, sheet, context, endpoint, arm):
    result = []
    for address in addresses:
        c = cells[address]
        check(f'literal:{file}:{sheet}:{address}', c['type'] == 'n' and not c['formula'] and c['token'] is not None)
        value = float(c['token'])
        check(f'finite:{file}:{sheet}:{address}', math.isfinite(value))
        result.append(value)
        measurements.append({'file': file, 'sheet': sheet, 'cell': address, 'context': context, 'endpoint': endpoint, 'arm': arm, 'native_token': c['token'], 'value': value})
    return np.array(result)


def welch_contrast(control, treatment, log=False):
    a, b = np.array(control, float), np.array(treatment, float)
    aa, bb = (np.log2(a), np.log2(b)) if log else (a, b)
    v1, v2 = aa.var(ddof=1) / len(aa), bb.var(ddof=1) / len(bb)
    se = math.sqrt(v1 + v2)
    df = (v1 + v2) ** 2 / (v1 ** 2 / (len(aa) - 1) + v2 ** 2 / (len(bb) - 1))
    effect = float(bb.mean() - aa.mean())
    interval = [float(effect - stats.t.ppf(.975, df) * se), float(effect + stats.t.ppf(.975, df) * se)]
    result = {'n_control': len(a), 'n_treated': len(b), 'control_mean': float(a.mean()), 'treated_mean': float(b.mean()), 'ratio_of_means': float(b.mean() / a.mean()), 'effect': effect, 'scale': 'log2' if log else 'native difference', 'unpaired_model_95ci': interval, 'welch_df': float(df), 'unpaired_welch_p': float(2 * stats.t.sf(abs(effect / se), df)), 'variance_terms': [float(v1), float(v2)]}
    if log:
        result['geometric_fold'] = float(2 ** effect)
        result['fold_95ci'] = [float(2 ** x) for x in interval]
    if len(a) + len(b) <= 10:
        joined = np.r_[aa, bb]
        null = []
        for idx in itertools.combinations(range(len(joined)), len(a)):
            mask = np.zeros(len(joined), dtype=bool)
            mask[list(idx)] = True
            null.append(float(joined[~mask].mean() - joined[mask].mean()))
        result['exact_unpaired_permutation_p'] = sum(abs(x) >= abs(effect) - 1e-12 for x in null) / len(null)
        result['permutation_assignments'] = len(null)
    leave = []
    for i in range(len(aa)):
        leave.append(float(bb.mean() - np.delete(aa, i).mean()))
    for i in range(len(bb)):
        leave.append(float(np.delete(bb, i).mean() - aa.mean()))
    result['leave_one_value_effect_range'] = [min(leave), max(leave)]
    return result


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False))


def save_tsv(name, rows):
    check(f'{name}:nonempty', bool(rows))
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter='\t')
        w.writeheader()
        w.writerows(rows)


# Direct PMP22 counter-screen, kept apart from stable-cell KCNQ1 contrasts.
jci = {'counter_screen': {}, 'cross_cargo': {}, 'five_compounds': [], 'kcnq1_variants': [], 'function_descriptive': [], 'viability': []}
name = 'JCI201297-data-native.xlsx'
columns = {'surface': ('C', 'D'), 'total': ('G', 'H'), 'fraction_percent': ('K', 'L')}
for cargo, sheet in [('KCNQ1', 'Sup. Fig. 4A'), ('PMP22', 'Sup. Fig. 4B')]:
    cells = literal_sheet(name, sheet)
    jci['counter_screen'][cargo] = {}
    for endpoint, (c, t) in columns.items():
        a = numbers(cells, [f'{c}{r}' for r in range(4, 7)], name, sheet, cargo, endpoint, 'DMSO')
        b = numbers(cells, [f'{t}{r}' for r in range(4, 7)], name, sheet, cargo, endpoint, 'VU0494372')
        jci['counter_screen'][cargo][endpoint] = welch_contrast(a, b, log=True)
for endpoint in columns:
    k = jci['counter_screen']['KCNQ1'][endpoint]
    p = jci['counter_screen']['PMP22'][endpoint]
    terms = k['variance_terms'] + p['variance_terms']
    effect = p['effect'] - k['effect']
    se = math.sqrt(sum(terms))
    df = sum(terms) ** 2 / sum(v ** 2 / 2 for v in terms)
    interval = [effect - stats.t.ppf(.975, df) * se, effect + stats.t.ppf(.975, df) * se]
    jci['cross_cargo'][endpoint] = {'estimand': 'PMP22 log2 effect minus KCNQ1 log2 effect', 'effect': effect, 'ratio_of_geometric_folds': 2 ** effect, 'unpaired_model_95ci': list(map(float, interval)), 'welch_df': df, 'assumption': 'All four groups independent; unknown cross-cargo/cross-arm covariance; selected compound; no confirmatory inference.'}
# All top-five follow-up hits, not only the favorable one.
wb = workbook(name)
for endpoint, sheet in [('surface', 'Sup. Fig. 3A'), ('total', 'Sup. Fig. 3B'), ('fraction_percent', 'Sup. Fig. 3C')]:
    ws = wb[sheet]
    cells = literal_sheet(name, sheet)
    for col in range(3, 8):
        c = openpyxl.utils.get_column_letter(col)
        compound = re.search(r'VU\d+', ws[f'{c}4'].value).group()
        a = numbers(cells, [f'B{r}' for r in range(5, ws.max_row + 1) if cells.get(f'B{r}', {}).get('type') == 'n' and cells[f'B{r}']['token'] is not None and not cells[f'B{r}']['formula']], name, sheet, 'stable KCNQ1', endpoint, 'DMSO')
        b = numbers(cells, [f'{c}{r}' for r in range(5, ws.max_row + 1) if cells.get(f'{c}{r}', {}).get('type') == 'n' and cells[f'{c}{r}']['token'] is not None and not cells[f'{c}{r}']['formula']], name, sheet, 'stable KCNQ1', endpoint, compound)
        jci['five_compounds'].append({'compound': compound, 'endpoint': endpoint, **welch_contrast(a, b, log=True)})
for endpoint, sheet in [('surface', 'Fig. 3A'), ('total', 'Fig. 3B'), ('fraction_percent', 'Fig. 3C')]:
    cells = literal_sheet(name, sheet)
    for variant, a_col, b_col in [('WT', 'F', 'L'), ('G179S', 'G', 'M'), ('G189E', 'H', 'N'), ('V207M', 'I', 'O')]:
        arrays = []
        for col, arm in [(a_col, 'DMSO'), (b_col, 'VU0494372 20uM')]:
            addresses = [f'{col}{r}' for r in range(5, 9)]
            arrays.append(numbers(cells, addresses, name, sheet, variant, endpoint, arm))
        jci['kcnq1_variants'].append({'variant': variant, 'endpoint': endpoint, **welch_contrast(*arrays, log=True)})
# Cell-level currents are described, not treated as independent cultures.
cells = literal_sheet(name, 'Fig. 5B')
for variant, ac, bc in [('WT', 'D', 'J'), ('G179S', 'E', 'K'), ('G189E', 'F', 'L'), ('V207M', 'G', 'M')]:
    result = {'variant': variant, 'unit': 'recorded cell; independent experiment nesting unavailable'}
    for col, arm in [(ac, 'DMSO'), (bc, 'VU0494372')]:
        addresses = [f'{col}{r}' for r in range(8, 132) if cells.get(f'{col}{r}', {}).get('type') == 'n' and cells[f'{col}{r}']['token'] is not None and not cells[f'{col}{r}']['formula']]
        x = numbers(cells, addresses, name, 'Fig. 5B', variant, 'current_density_pA_per_pF', arm)
        result[arm] = {'n_cells': len(x), 'mean': float(x.mean()), 'median': float(np.median(x)), 'range': [float(x.min()), float(x.max())]}
    result['ratio_of_means'] = result['VU0494372']['mean'] / result['DMSO']['mean']
    jci['function_descriptive'].append(result)
cells = literal_sheet(name, 'Fig. 4D')
for label, col in [('DMSO_0.1pct', 'F'), ('DMSO_0.2pct', 'G'), ('VU10uM', 'I'), ('VU20uM', 'K')]:
    x = numbers(cells, [f'{col}{r}' for r in range(5, 8)], name, 'Fig. 4D', 'stable KCNQ1', 'percent_live', label)
    jci['viability'].append({'condition': label, 'values': x.tolist(), 'mean': float(x.mean())})
wb.close()
save_json('jci-contrasts.json', jci)

# Two-repeat, selected general-cargo screen with local negative controls.
wb = workbook('CAM40408-S4.xlsx')
rows = list(wb['Sheet1'].iter_rows(values_only=True))[1:]
wb.close()
check('HRP all rows six typed values', all(len(r) == 6 and isinstance(r[3], (int, float)) and isinstance(r[4], (int, float)) for r in rows))
plates = defaultdict(list)
for r in rows:
    plates[(r[0], r[5])].append(r)
normalized = []
controls = []
for (plate, repeat), data in plates.items():
    bg = np.array([[r[3], r[4]] for r in data if r[2] == 'No_cell_control'])
    nt = np.array([[r[3], r[4]] for r in data if r[2].startswith('ON-TARGETplus')])
    un = np.array([[r[3], r[4]] for r in data if r[2] == 'No_treatment_control'])
    check(f'{plate}/{repeat} controls', len(bg) == 8 and len(nt) == 2 and len(un) == 8)
    controls.append({'plate': plate, 'repeat': repeat, 'no_cell_mean_CL_SN': bg.mean(0).tolist(), 'NT_values_CL_SN': nt.tolist(), 'no_treatment_mean_CL_SN': un.mean(0).tolist()})
    modes = [('mean_background_mean_NT', bg.mean(0), nt.mean(0)), ('median_background_mean_NT', np.median(bg, 0), nt.mean(0)), ('NT1_only', bg.mean(0), nt[0]), ('NT2_only', bg.mean(0), nt[1]), ('untreated_comparator', bg.mean(0), un.mean(0))]
    for r in data:
        if 'ontrol' in r[2]:
            continue
        for mode, background, control in modes:
            corrected = np.array(r[3:5], float) - background
            denominator = control - background
            valid = bool((corrected > 0).all() and (denominator > 0).all())
            cl, sn = corrected / denominator
            normalized.append({'gene': r[2], 'plate': plate, 'well': r[1], 'repeat': repeat, 'normalization': mode, 'raw_CL': r[3], 'raw_SN': r[4], 'valid_positive': valid, 'CL_fold': float(cl) if valid else None, 'SN_fold': float(sn) if valid else None, 'SN_over_CL_fold': float(sn / cl) if valid else None})
bygene = defaultdict(list)
for r in normalized:
    bygene[r['gene']].append(r)
golgi = {}
wb = workbook('CAM40408-S6.xlsx')
groups = defaultdict(list)
golgi_missing = []
for source_row, r in enumerate(list(wb.worksheets[0].iter_rows(values_only=True))[1:], 2):
    if not all(isinstance(x, (int, float)) for x in r[3:6]):
        check('Golgi explicit missing tokens only', r[3:6] == ('na', 'na', 'na'))
        golgi_missing.append({'source_row': source_row, 'well': r[0], 'gene': r[1], 'image': r[2], 'tokens': list(r[3:6])})
        continue
    check('Golgi cell counts reconcile', r[3] == r[4] + r[5])
    groups[(r[0], r[1])].append(r)
wb.close()
for (well, gene), data in groups.items():
    total = sum(r[3] for r in data)
    fraction = sum(r[4] for r in data) / total
    golgi.setdefault(gene, []).append({'well': well, 'images': len(data), 'missing_images': sum(x['well'] == well for x in golgi_missing), 'cells': total, 'fragmented_fraction': fraction})
control_golgi = sum(x['fragmented_fraction'] for x in golgi['Control']) / len(golgi['Control'])
hrp_results = []
for gene, data in sorted(bygene.items()):
    main = sorted([x for x in data if x['normalization'] == 'mean_background_mean_NT'], key=lambda x: x['repeat'])
    check(f'{gene}:two repeats', [x['repeat'] for x in main] == [1, 2])
    valid = all(x['valid_positive'] for x in main)
    gain = valid and all(x['SN_fold'] >= 1.25 and x['SN_over_CL_fold'] >= 1.25 for x in main)
    loss = valid and all(x['SN_fold'] <= .75 and x['SN_over_CL_fold'] <= .8 for x in main)
    robust = all(x['valid_positive'] and x['SN_fold'] >= 1.25 and x['SN_over_CL_fold'] >= 1.25 for x in data if x['normalization'] != 'untreated_comparator')
    result = {'gene': gene, 'valid': valid, 'gain_rule': gain, 'gain_robust_to_NT_and_background': robust, 'loss_rule': loss, 'SN_fold_repeat1': main[0]['SN_fold'], 'SN_fold_repeat2': main[1]['SN_fold'], 'CL_fold_repeat1': main[0]['CL_fold'], 'CL_fold_repeat2': main[1]['CL_fold'], 'SN_CL_fold_repeat1': main[0]['SN_over_CL_fold'], 'SN_CL_fold_repeat2': main[1]['SN_over_CL_fold'], 'golgi_wells': len(golgi.get(gene, [])), 'golgi_fragmented_fraction': golgi[gene][0]['fragmented_fraction'] if gene in golgi else None, 'golgi_control_mean_fraction': control_golgi}
    hrp_results.append(result)
hrp_summary = {'source_rows': len(rows), 'distinct_perturbation_labels': len(bygene), 'selected_followup_universe_not_genome': True, 'controls': controls, 'gain_candidates': [x['gene'] for x in hrp_results if x['gain_rule']], 'robust_gain_candidates': [x['gene'] for x in hrp_results if x['gain_robust_to_NT_and_background']], 'loss_candidates': [x['gene'] for x in hrp_results if x['loss_rule']], 'invalid_positive_genes': [x['gene'] for x in hrp_results if not x['valid']], 'PMP22_cargo_measured': False, 'PMP22_target_present': 'PMP22' in bygene, 'RER1_UGGT1_LMAN1_target_coverage': {g: g in bygene for g in ['RER1', 'UGGT1', 'LMAN1']}, 'golgi': golgi, 'golgi_unit': 'well; images and cells are subsamples, typically one well/target', 'limitations': 'No viable-cell count in HRP wells, no protein mass assay, two repeats, selected siRNA pools, no addback or independent-gene reagent replication; orthogonal same-study Golgi not independent biological validation.'}
save_tsv('hrp-well-contrasts.tsv', normalized)
save_tsv('hrp-gene-contrasts.tsv', hrp_results)
hrp_summary['golgi_missing_images'] = golgi_missing
save_json('hrp-summary.json', hrp_summary)

# Literal pulse-chase values; N57 has a date display format but is stored as numeric.
name = 'elife-63997-fig5-data1.xlsx'
cells = literal_sheet(name, 'Sheet1')
uggt = {'pulse': {}, 'contrasts_2h': [], 'steady_state': [], 'date_style_cell': {'cell': 'N57', **cells['N57']}}
for group, start in [('WT', 12), ('UGGT1_KO', 15), ('UGGT2_KO', 18), ('UGGT1_2_KO', 21), ('ALG6_KO', 24), ('ALG6_KO_DNJ', 27), ('WT_no_DNJ', 30), ('WT_DNJ', 33)]:
    series = []
    for r in range(56, 59):
        x = numbers(cells, [f'{openpyxl.utils.get_column_letter(c)}{r}' for c in range(start, start + 3)], name, 'Sheet1', group, 'pulse_labeled_mature_fraction_percent', f'biological_series_row_{r}')
        series.append(x.tolist())
    uggt['pulse'][group] = {'values_0_1_2h': series, 'mean_0_1_2h': np.mean(series, axis=0).tolist(), 'change_0_to_2h': [v[2] - v[0] for v in series]}
for control, treatment in [('WT', 'UGGT1_KO'), ('WT', 'UGGT2_KO'), ('WT', 'UGGT1_2_KO'), ('WT', 'ALG6_KO'), ('ALG6_KO', 'ALG6_KO_DNJ'), ('WT_no_DNJ', 'WT_DNJ'), ('UGGT2_KO', 'UGGT1_KO')]:
    a = [x[2] for x in uggt['pulse'][control]['values_0_1_2h']]
    b = [x[2] for x in uggt['pulse'][treatment]['values_0_1_2h']]
    uggt['contrasts_2h'].append({'control': control, 'treatment': treatment, **welch_contrast(a, b), 'change_0_to_2h_contrast': welch_contrast(uggt['pulse'][control]['change_0_to_2h'], uggt['pulse'][treatment]['change_0_to_2h'])})
# Within-lane ratios computed from native intensities, not source formulas.
for cargo, pairs in [('IGF1R', [(19, 20, 'N', 'O'), (19, 20, 'P', 'Q'), (24, 25, 'N', 'O'), (24, 25, 'P', 'Q')]), ('HEXB', [(31, 32, 'N', 'O'), (31, 32, 'P', 'Q'), (36, 37, 'N', 'O'), (36, 37, 'P', 'Q')])]:
    fractions = {'no_DNJ': [], 'DNJ': []}
    for pro_row, mature_row, control_col, treat_col in pairs:
        for col, arm in [(control_col, 'no_DNJ'), (treat_col, 'DNJ')]:
            pro, mature = numbers(cells, [f'{col}{pro_row}', f'{col}{mature_row}'], name, 'Sheet1', cargo, 'steady_state_native_band_intensity', arm)
            fractions[arm].append(float(100 * mature / (pro + mature)))
    uggt['steady_state'].append({'cargo': cargo, 'fractions_percent': fractions, 'fraction_contrast': welch_contrast(fractions['no_DNJ'], fractions['DNJ']), 'absolute_band_amount_comparability': 'unestablished; fraction only'})
# Full quantitative-capture universe versus annotation background.
coverage = []
for file in ['elife-63997-supp1.xlsx', 'elife-63997-supp2.xlsx', 'elife-63997-fig4-data1.xlsx']:
    wb = workbook(file)
    for ws in wb:
        hits = []
        accession_rows = set()
        for row in ws:
            for c in row:
                value = c.value
                if isinstance(value, str) and (value == 'Q01453' or 'GN=PMP22 ' in value):
                    hits.append({'cell': c.coordinate, 'value': value})
                if isinstance(value, str) and re.fullmatch(r'[A-Z0-9]{6,10}', value):
                    accession_rows.add(c.row)
        coverage.append({'file': file, 'sheet': ws.title, 'rows': ws.max_row, 'PMP22_exact_hits': hits, 'approx_accession_bearing_rows_not_universe_definition': len(accession_rows)})
    wb.close()
uggt['coverage'] = coverage
uggt['limits'] = 'PMP22 in annotation universe is not measured PMP22. Pulse-chase fraction concerns surviving immunoprecipitated IGF1R, not absolute initial-cohort yield; steady-state and chase are separate. No cross-genotype donor pairing assumed. No native formulas evaluated.'
save_json('uggt-maturation.json', uggt)
save_tsv('native-measurements.tsv', measurements)
# Detect exact repeated measurement vectors; do not count reused figures as replication.
check('direct PMP22 native scalar count', sum(x['context'] == 'PMP22' for x in measurements) == 18)
check('UGGT numeric date token in percentage domain', 0 < float(cells['N57']['token']) < 100)
check('HRP full universe repeated twice', len(rows) - 180 == 2 * len(bygene))
save_json('analysis-validation.json', {'valid': all(x['passed'] for x in checks), 'checks': checks, 'input_hashes': used, 'native_measurements': len(measurements), 'formula_execution': False, 'biological_replication': False, 'methods': 'numpy/scipy calculations on native scalar exports; independent contrasts unless explicit within-series endpoint; no downloaded code execution'})
print(json.dumps({'PMP22': jci['counter_screen']['PMP22'], 'cargo_interaction': jci['cross_cargo'], 'HRP': {k: hrp_summary[k] for k in ['distinct_perturbation_labels', 'gain_candidates', 'robust_gain_candidates', 'loss_candidates']}, 'UGGT_2h': uggt['contrasts_2h']}, indent=2))
