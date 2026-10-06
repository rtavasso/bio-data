"""Print final source estimates without re-fitting or rounding stored tables."""
import json
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
x=json.loads((Q/'outputs/final-r002/results-summary.json').read_text())
for r in x['selected_CI_rows']:
    print(r['assay'],r['tissue'],'n',r['sample_n'],'beta',r['beta'],'CI',r['ci95_normal_low'],r['ci95_normal_high'],'p',r['pval_nominal'],'q',r['qval'])
print('GENCORD',x['GENCORD_primary_CI'])
print('Novelty SNP',json.loads((Q/'inputs/public/novelty-rs231016.json').read_text())['hitCount'])
