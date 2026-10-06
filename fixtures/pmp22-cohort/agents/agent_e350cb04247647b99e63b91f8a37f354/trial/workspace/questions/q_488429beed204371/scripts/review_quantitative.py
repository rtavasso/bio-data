"""Compact quantitative review of executed tables, including adverse sensitivities."""
import csv
import json
import statistics as st
from pathlib import Path

q = Path(__file__).resolve().parents[1]
o = q/'outputs'

def rows(name):
    with (o/name).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))

summary = json.loads((o/'summary.json').read_text())
print('ROBUSTNESS', json.dumps(summary['robustness'],indent=2))
for r in rows('comparator-contrasts.tsv'):
    if r['method']=='none' and r['strategy']=='all_selected_clusters_sum':
        print('COMPARATOR',r['contrast'],r['gene'],'mean',r['control_mean_RPM'],r['treated_mean_RPM'],'log2FC',r['log2_fold_of_means'])
for r in rows('contrasts-and-sensitivity.tsv'):
    if r['set']=='focal':
        print('FOCAL',r['contrast'],r['method'],r['constant_RPM'],'mean-ratio-difference',r['P1_minus_P2_log2_fold_of_means'],'mean-logratio-difference',r['change_mean_log2_P1_P2'])
for contrast in ['cAMP_vs_vehicle','SOX10_KO_vs_parental']:
    rr = [r for r in rows('leave-one-library.tsv') if r['contrast']==contrast]
    for key in ['P1_minus_P2_log2_fold_of_means','change_mean_log2_P1_P2']:
        usable = [r for r in rr if r[key]!='NA']
        extremes = sorted(usable,key=lambda r:float(r[key]))
        print('ALL_LOO_EXTREMES',contrast,key,'defined',len(usable),'of',len(rr))
        for r in [extremes[0],extremes[-1]]:
            print({k:r[k] for k in ['set','method','constant_RPM','omitted_library',key]})
for condition in ['adult_nerve','primary_control','primary_cAMP','S16_parental','S16_SOX10_KO']:
    rr = [r for r in rows('per-library-start-signals.tsv') if r['set']=='focal' and r['condition']==condition]
    print('COMPOSITION',condition, {k:st.mean([float(r[k]) for r in rr]) for k in ['P1_fraction_focal_or_window_pair','P1_fraction_all22','P2_fraction_all22']})
print('PER_CLUSTER', [(r['cluster_id'], r['contrast'], r['control_mean_RPM'], r['treated_mean_RPM'], r['log2_fold_of_means_no_pseudocount']) for r in rows('all-pmp22-cluster-contrasts.tsv')])
