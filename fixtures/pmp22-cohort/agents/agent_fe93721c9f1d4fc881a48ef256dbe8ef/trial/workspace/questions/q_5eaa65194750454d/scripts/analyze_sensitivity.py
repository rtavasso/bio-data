"""Post-hoc multiplicity and baseline sensitivity; not a new discovery test."""
import json
from pathlib import Path
from scipy import stats
q=Path(__file__).resolve().parents[1]
sets=[]
for f in ['executed-contrasts.json','followup-contrasts.json']:
    sets += json.loads((q/'outputs'/f).read_text())['contrasts']
family=len(sets)*2
out=[]
for ds in sets:
    primary=ds['variants'][ds['primary']]
    regulators={}
    for g in ['Egr2','Sox10']:
        r=primary[g]
        half=float(stats.t.ppf(1-.05/(2*family),r['df'])*r['se'])
        ci=[r['effect']-half,r['effect']+half]
        regulators[g]={'family14_ci95':ci,'contained_pm0.5':ci[0]>=-.5 and ci[1]<=.5}
    out.append({'contrast':ds['id'],'regulators':regulators,'both_pm0.5_family14':all(r['contained_pm0.5'] for r in regulators.values()),
                'both_pm0.5_all_normalizations_nominal':all(v[g]['preserved_0.5'] for v in ds['variants'].values() for g in ['Egr2','Sox10']),
                'secondary_panel_floor_failures':{panel:[g for g in genes if not ds['coverage'][g]['eligible']] for panel,genes in json.loads((q/'inputs/analysis-plan.r001.json').read_text())['controls'].items()}})
r={'family_size':family,'method':'Bonferroni family of Egr2/Sox10 changes across seven inspected RNA contrasts; post-hoc sensitivity, library/pool independence assumptions unchanged','results':out}
(q/'outputs/preservation-sensitivity.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
print(json.dumps(r,indent=2))
