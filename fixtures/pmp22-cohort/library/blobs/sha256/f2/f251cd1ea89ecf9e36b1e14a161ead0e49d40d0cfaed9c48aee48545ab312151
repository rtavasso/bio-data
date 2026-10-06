"""Compile verified contrasts, sensitivity tables and plots; independently check CIs."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

Q=Path(__file__).resolve().parents[1]
all_sets=[]
for filename in ['executed-contrasts.json','followup-contrasts.json']:
    all_sets += json.loads((Q/'outputs'/filename).read_text())['contrasts']
samples=pd.concat([pd.read_csv(Q/'outputs'/f,sep='\t') for f in ['sample-expression.tsv','followup-sample-expression.tsv']],ignore_index=True)
plan=json.loads((Q/'inputs/analysis-plan.r001.json').read_text())
panel=plan['primary_program']['genes']
coverage=[]
summary=[]
components=[]
verified=0
for ds in all_sets:
    c,t=ds['control'],ds['treatment']
    for gene,r in ds['coverage'].items():
        coverage.append({'contrast':ds['id'],'gene':gene,'eligible':r['eligible'],'native_feature_matches':r.get('native_matches',r.get('matches')),'native_feature_ids':';'.join(r['feature_ids']),'control_min_native':r.get('control_min_native'),'source_units':ds['units']})
    for variant,results in ds['variants'].items():
        d=samples[(samples.contrast==ds['id']) & (samples.variant==variant)]
        wide=d.pivot(index='sample',columns='gene',values='log2_expression')
        for metric,r in results.items():
            if metric in wide:
                v=wide[metric]
            elif metric=='myelin7':
                v=wide[panel].mean(axis=1)
            elif '-minus-' in metric:
                lhs,rhs=metric.split('-minus-')
                v=(wide[panel].mean(axis=1) if lhs=='myelin7' else wide[lhs])-wide[rhs]
            else:
                v=wide[plan['controls'][metric]].mean(axis=1)
            scipy_test=stats.ttest_ind(v.loc[t],v.loc[c],equal_var=False)
            interval=scipy_test.confidence_interval(.95)
            assert np.allclose([interval.low,interval.high],r['ci95'],rtol=1e-9,atol=1e-10)
            assert np.isclose(v.loc[t].mean()-v.loc[c].mean(),r['effect'])
            verified+=1
            summary.append({'contrast':ds['id'],'variant':variant,'primary':variant==ds['primary'],'metric':metric,
                            'log2_change':r['effect'],'ci_low':r['ci95'][0],'ci_high':r['ci95'][1],
                            'preserved_0.25':r['preserved_0.25'],'preserved_0.5':r['preserved_0.5'],'nondepleted_0.5':r['nondepleted_0.5'],
                            'minimum_symmetric_bound':r['minimum_symmetric_bound']})
        if variant==ds['primary']:
            for g in panel+sum(plan['controls'].values(),[]):
                components.append({'contrast':ds['id'],'gene':g,'log2_change':float(wide.loc[t,g].mean()-wide.loc[c,g].mean())})
summary=pd.DataFrame(summary)
summary.to_csv(Q/'outputs/integrated-contrasts.tsv',sep='\t',index=False)
pd.DataFrame(coverage).to_csv(Q/'outputs/feature-eligibility.tsv',sep='\t',index=False)
pd.DataFrame(components).to_csv(Q/'outputs/program-components.tsv',sep='\t',index=False)

rank_order=['Nedd4_cKO_P5','Rnf40_cKO_P14','RaptorKO_P5','Tead1_cKO_P50','Nae1_cKO_P7','PTENKO_P5','TSC1KO_P5','NRG1_6h']
reasons={
'Nedd4_cKO_P5':'Best both-RNA bounded-preservation example at +/-0.5, not +/-0.25. Modest program fall; stronger frozen shared-pattern criterion fails.',
'Rnf40_cKO_P14':'Strong Egr2-nondepleted RNA/program discordance with source functional cofactor/chromatin evidence. Sox10 decreases; both-regulator prediction fails.',
'RaptorKO_P5':'Robust Egr2-nondepleted RNA/program discordance; Sox10 bounds inconclusive. Mechanism/direction already published.',
'Tead1_cKO_P50':'Orthogonal Krox20-high/MPZ-MBP-low protein evidence only. Not a preserved-RNA/PMP22 comparison.',
'Nae1_cKO_P7':'Known protein-persistence mechanism, but both regulator RNAs decrease in nerve; not RNA preservation.',
'PTENKO_P5':'Egr2 RNA depletion; shared controls with Tsc1/Raptor. Not both-RNA preserved.',
'TSC1KO_P5':'Egr2 RNA depletion; shared controls with Pten/Raptor. Not both-RNA preserved.',
'NRG1_6h':'Egr2 RNA depletion in culture; Sox10 uncertainty wide. Not preserved Egr2 despite near-zero Sox10 point estimate.'}
ranked=[]
for rank,identifier in enumerate(rank_order,1):
    ds=next((d for d in all_sets if d['id']==identifier),None)
    row={'rank':rank,'candidate':identifier,'interpretation':reasons[identifier]}
    if ds:
        for metric in ['Egr2','Sox10','Pmp22','myelin7','myelin7-minus-Egr2','myelin7-minus-Sox10']:
            r=ds['variants'][ds['primary']][metric]
            row[metric]=f"{r['effect']:+.3f} [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]"
        row['both_RNA_95CI_within_pm0.5']=all(ds['variants'][ds['primary']][g]['preserved_0.5'] for g in ['Egr2','Sox10'])
    ranked.append(row)
pd.DataFrame(ranked).to_csv(Q/'outputs/ranked-upstream-candidates.tsv',sep='\t',index=False)

fig,axes=plt.subplots(1,4,figsize=(14,6),sharey=True)
order=[r for r in rank_order if r!='Tead1_cKO_P50']
for ax,metric in zip(axes,['Egr2','Sox10','myelin7','Pmp22'],strict=True):
    for y,identifier in enumerate(order):
        r=summary[(summary.contrast==identifier)&summary.primary&(summary.metric==metric)].iloc[0]

        ax.errorbar(r.log2_change,y,xerr=[[r.log2_change-r.ci_low],[r.ci_high-r.log2_change]],fmt='o',color='#30343b',capsize=3)
    ax.axvline(0,color='gray',lw=.8)
    if metric in ['Egr2','Sox10']:
        ax.axvspan(-.5,.5,color='#a8dadc',alpha=.4)
    ax.set_title(metric)
    ax.set_xlabel('Perturbed − control, log2 (95% CI)')
axes[0].set_yticks(range(len(order)),order)
axes[0].invert_yaxis()
fig.suptitle('Upstream contrasts: RNA abundance, fixed output proxy and Pmp22\nUnpaired source-unit intervals; contexts not pooled; score is not TF activity')
fig.tight_layout()
fig.savefig(Q/'outputs/upstream-discordance.png',dpi=180)
plt.close(fig)

for name in ['parent-assay-critique-answer','mechanics-reply-post','proposal-late-readback']:
    d=json.loads((Q/f'outputs/{name}.json').read_text())
    (Q/f'outputs/{name}.body.md').write_text(d['content']['body'])

# Runner output/hash integrity and exact numerical reproduction after lint-only fix.
receipt_names=['execution-r002.json','followup-execution-r002.json','tead-execution-r001.json']
checks=[]
for name in receipt_names:
    r=json.loads((Q/'outputs'/name).read_text())
    assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
    assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest()==r['code_sha256']
    for item in r['outputs']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    checks.append(name)
a=json.loads((Q/'outputs/execution-r001.json').read_text())
b=json.loads((Q/'outputs/execution-r002.json').read_text())
assert [o['sha256'] for o in a['outputs']]==[o['sha256'] for o in b['outputs']]
report={'verified_CI_estimates_against_scipy':verified,'RNA_contrasts':len(all_sets),'ranked_candidates':len(ranked),
        'producer_receipts_verified':checks,'lint_only_rerun_scientific_bytes_identical':True,
        'RNA_preservation_is_relative_not_absolute_per_cell':True,'program_excludes_Pmp22_Egr2_Sox10':not bool(set(panel)&set(plan['targets']))}
(Q/'outputs/numerical-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
print(summary[(summary.contrast.isin(['Nedd4_cKO_P5','Rnf40_cKO_P14'])) & (summary.metric.isin(['Egr2','Sox10','myelin7','Pmp22','cycle6']))].to_string(index=False))
print(pd.DataFrame(components).query("contrast in ['Nedd4_cKO_P5','Rnf40_cKO_P14']").to_string(index=False))
