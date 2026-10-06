"""Independent checks of source contrasts, full denominators and producing receipt."""
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import scipy.stats as st

q = Path(__file__).resolve().parents[1]
o = q/'outputs/independent-r001'
rp = q/'outputs/execution-independent-r006.json'
receipt = json.loads(rp.read_text())
assert receipt['complete'] and receipt['exit_code'] == 0 and receipt['code_unchanged']
assert hashlib.sha256((q/'scripts/analyze_independent_pum.py').read_bytes()).hexdigest() == receipt['code_sha256']
for r in receipt['outputs']:
    assert r['written'] and hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() == r['sha256']
s = json.loads((o/'summary.json').read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
bg = json.loads((o/'complete-backgrounds.json').read_text())
with (o/'all-feature-endpoints.tsv').open() as f:
    count = sum(1 for _ in csv.DictReader(f, delimiter='\t'))
expected = sum(x.get('all_source_genes', x.get('gene_summary_rows', x.get('source_loci',0))) for x in bg)
assert count == expected
rows = list(csv.DictReader((o/'bruchase-native-coefficients.tsv').open(), delimiter='\t'))
prefix = 'conditiontime_interaction_term_'
eligible = [r for r in rows if r[prefix+'padj'] != 'NA']
assert len(eligible) == 10132
ps = [float(r[prefix+'pvalue']) for r in eligible]
qs = st.false_discovery_control(ps, method='bh')
max_qerror = max(abs(float(r[prefix+'padj']) - float(v)) for r,v in zip(eligible,qs,strict=True))
assert max_qerror < 1e-10
r = next(r for r in rows if r['Gene'] == 'PMP22')
lfc, se, z = [float(r[prefix+field]) for field in ['log2FoldChange','lfcSE','stat']]
assert math.isclose(lfc/se,z, rel_tol=1e-12)
assert math.isclose(2*st.norm.sf(abs(z)),float(r[prefix+'pvalue']),rel_tol=1e-12)
assert s['prediction']['status'] == 'failed'
assert s['prediction']['source_feature_class'] == 'NOEFFECT'
assert s['prediction']['observed']['ci95_lower'] < 0 < s['prediction']['observed']['ci95_upper']
assert s['prediction']['observed']['ci95_upper'] < math.log2(1.75)
# This last diagnostic is source-ROPE context, not a newly predeclared equivalence success.
for r in s['target_results']:
    if r['study'] == 'GSE123016':
        assert r['source_status'] == 'OK'
        assert r['source_log2_ratio_discrepancy'] < .003
        assert abs(math.log2(r['numerator_fpkm']/r['denominator_fpkm'])-r['log2_effect']) < .003
    if r['study'] == 'GSE159510':
        assert r['control_mean'] > 5 and r['intervention_mean'] > 5
        assert r['splicing_APA_flag'] == 'No' and r['tandem_APA_flag'] == 'No'
        assert r['ci95_lower'] is None and r['ci95_upper'] is None
assert len(s['target_results']) == 13
assert all(not r['joint_strict_candidate'] for r in s['tcam_binding_adjudication'])
assert len(s['sample_file_inventory']) == 21
assert all(x['rows'] == x['unique_refseq'] for x in s['sample_file_inventory'])
checks = {'all_checks_passed': True, 'analysis_execution_receipt_sha256': hashlib.sha256(rp.read_bytes()).hexdigest(),
          'rows': count, 'expected_background_rows': expected, 'pmp22_endpoint_rows': len(s['target_results']),
          'source_BH_reconstructed_genes': len(eligible), 'maximum_source_BH_discrepancy': max_qerror,
          'tcam_ratio_warning_count': len(s['tcam_source_ratio_warnings']),
          'ratio_warning_examples': s['tcam_source_ratio_warnings'][:3],
          'source_equivalence_threshold_log2': math.log2(1.75),
          'pmp22_relative_persistence_fold_ci95': [2**(lfc-NormalDist().inv_cdf(.975)*se),2**(lfc+NormalDist().inv_cdf(.975)*se)],
          'caution': 'Checks validate extraction/computation and source consistency, not causal truth, raw-count fit, or cell-context transfer.'}
(q/'outputs/verification-independent-r002.json').write_text(json.dumps(checks,indent=2,allow_nan=False))
print(json.dumps(checks,allow_nan=False))
