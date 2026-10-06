"""Independent finite/schema/provenance checks on the final local products."""
import csv
import hashlib
import json
import math
import os
import platform
import sys
from pathlib import Path
import scipy
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def fail_constant(x):
    raise ValueError(x)
receipts=[]
for name in ['paired-execution-r001','audit-execution-r001']:
    obj=json.loads((q/f'outputs/{name}.json').read_text(),parse_constant=fail_constant)
    assert obj['exit_code']==0 and obj['complete'] and obj['code_unchanged']
    assert sha(Path(obj['producer']))==obj['code_sha256']
    for output in obj['outputs']:
        assert output['written'] and sha(Path(output['path']))==output['sha256']
    receipts.append({'receipt':name,'output_hashes_match':True,'producer_hash_matches':True})
audit=json.loads((q/'outputs/sample-unit-audit.json').read_text(),parse_constant=fail_constant)
paired=json.loads((q/'outputs/paired-audit-summary.json').read_text(),parse_constant=fail_constant)
assert len(audit['sample_annotations'])==audit['validation']['sample_rows']
with (q/'outputs/sample-units.tsv').open() as f:
    assert len(list(csv.DictReader(f,delimiter='\t')))==audit['validation']['sample_rows']
with (q/'outputs/paired-subject-effects.tsv').open() as f:
    diffs=list(csv.DictReader(f,delimiter='\t'))
for row in paired['primary']:
    observed=[float(x['difference_log2_nmSC_minus_mSC']) for x in diffs if x['endpoint']==row['endpoint']]
    assert len(observed)==4
    assert math.isclose(sum(observed)/4,row['effect_log2'],abs_tol=1e-12)
    assert all(math.isfinite(x) for x in observed)
    assert row['ci95_low']<=row['effect_log2']<=row['ci95_high']
    assert 0<=row['signflip_p_two_sided']<=1
assert all(not x['nae1_within_state_eligible'] for x in audit['sample_annotations'])
result={'checks':'passed','sample_rows':len(audit['sample_annotations']),'paired_endpoints':len(paired['primary']),'receipts':receipts,'reused_source_agreement':paired['agreement_checks'],'environment':{'python':sys.version,'platform':platform.platform(),'scipy':scipy.__version__},'not_verified':['No biological replication claimed','Supplement handling-control values unavailable','No gene-level genotype-matched P7 compartment estimate']}
(q/'outputs/verification.json').write_text(json.dumps(result,indent=2,allow_nan=False))
(q/'outputs/environment.json').write_text(json.dumps(result['environment'],indent=2))
print(json.dumps(result,indent=2))
