"""Independent consistency checks of saved numeric outputs and source identities."""
import hashlib
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'


def test_execution_receipts_and_hashes():
    for name in ['rna-execution-r001.json','rna-summary-execution-r001.json','transfer-execution-r001.json']:
        r = json.loads((OUT/name).read_text())
        assert r['complete'] and r['exit_code'] == 0 and r['code_unchanged']
        assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest() == r['code_sha256']
        for item in r['outputs']:
            assert item['written']
            assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']


def test_all_source_backgrounds_retained():
    table = pd.read_csv(OUT/'rna-all-gene-contrasts.tsv.gz', sep='\t')
    for name, contexts in [('Acly',['GSE252209_5wk']), ('CMT',['GSE115930_E21','GSE115930_P6','GSE115930_P18'])]:
        a = json.loads((OUT/f'{name}-acquired.json').read_text())
        native = pd.read_csv(a['path'], compression='gzip', sep=',' if name=='Acly' else '\t')
        for context in contexts:
            subset = table[table.contrast == context]
            assert len(subset) == len(native)
            assert subset.gene_id.tolist() == native.gene_id.tolist()


def test_program_effects_and_permutations_from_saved_samples():
    samples = pd.read_csv(OUT/'rna-per-sample.tsv', sep='\t')
    programs = pd.read_csv(OUT/'rna-program-contrasts.tsv', sep='\t')
    for row in programs.itertuples():
        s = samples[(samples.contrast == row.contrast) & (samples.endpoint == row.endpoint)]
        a = s[s.group == 'perturbed'].value_log2.to_numpy()
        b = s[s.group == 'control'].value_log2.to_numpy()
        observed = a.mean()-b.mean()
        assert np.isclose(observed, row.delta_log2, atol=1e-12)
        pooled = np.r_[a,b]
        perm = []
        for combo in combinations(range(len(pooled)), len(a)):
            selected = np.array(combo)
            rest = np.setdiff1d(np.arange(len(pooled)), selected)
            perm.append(pooled[selected].mean()-pooled[rest].mean())
        p = np.mean(np.abs(perm) >= abs(observed)-1e-12)
        assert np.isclose(p,row.permutation_p)


def test_discovery_ratios_cancel_common_normalization():
    s = pd.read_csv(OUT/'rna-per-sample.tsv', sep='\t')
    for _, group in s[s.endpoint.isin(['gene:Abca1','gene:Abcg1'])].groupby('contrast'):
        x = group.pivot(index='sample', columns='endpoint', values='normalized_count')
        expected = np.log2((x['gene:Abca1']+.5)/(x['gene:Abcg1']+.5))
        logged = group.pivot(index='sample', columns='endpoint', values='value_log2')
        assert np.allclose(expected,logged['gene:Abca1']-logged['gene:Abcg1'])


def test_frozen_validation_rule_not_relaxed():
    v = json.loads((OUT/'validation-transfer.json').read_text())
    lock = OUT/'predictions/abca1-abcg1-state-transfer-r001.json'
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == v['prediction_sha256']
    assert v['genes']['Abcg1']['control_mean_normalized'] < 10
    assert v['result_status'] == 'untestable' and not v['eligible']
    assert len(v['samples']) == 6 and sum(x['treatment'] for x in v['samples']) == 3
    assert v['primary_logratio']['permutation_assignments'] == 20


def test_sensitivity_does_not_reverse_key_sterol_relative_directions():
    s = pd.read_csv(OUT/'rna-sensitivities.tsv', sep='\t')
    s = s[s.endpoint == 'sterol_synthesis_minus_myelin7']
    assert (s[s.contrast == 'GSE115930_P18'].delta_log2 < 0).all()
    assert (s[s.contrast == 'GSE252209_5wk'].delta_log2 > 0).all()


def test_native_acly_group_mapping_checked():
    m = json.loads((OUT/'Acly-group-mapping-validation.json').read_text())
    assert m['matched_raw_columns'] and m['AK_group'] == 'Aclyko' and m['AW_group'] == 'Aclywt'
