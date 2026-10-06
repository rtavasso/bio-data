"""Independent output checks, sensitivity summaries and native-source consistency audit."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'inputs/public'
OUT=ROOT/'outputs'
checks=[]

def require(name, condition):
    checks.append({'check':name,'passed':bool(condition)})
    assert condition,name

def load(name):
    return json.loads((OUT/name).read_text())

receipt=load('execution-r002.json')
require('producer finished',receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged'])
for r in receipt['outputs']:
    require('output hash '+Path(r['path']).name,hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'])
wb=openpyxl.load_workbook(P/'JCI201297-data-native.xlsx',read_only=True,data_only=False,keep_links=False)
j=load('jci-contrasts.json')
for cargo,sheet in [('KCNQ1','Sup. Fig. 4A'),('PMP22','Sup. Fig. 4B')]:
    for ep,c,t in [('surface','C','D'),('total','G','H'),('fraction_percent','K','L')]:
        x=np.array([wb[sheet][f'{c}{r}'].value for r in [4,5,6]])
        y=np.array([wb[sheet][f'{t}{r}'].value for r in [4,5,6]])
        value=float(np.log2(y).mean()-np.log2(x).mean())
        require('direct native geometric effect '+cargo+ep,math.isclose(value,j['counter_screen'][cargo][ep]['effect'],abs_tol=1e-12))
wb.close()
with (OUT/'hrp-well-contrasts.tsv').open() as f:
    wells=list(csv.DictReader(f,delimiter='\t'))
with (OUT/'hrp-gene-contrasts.tsv').open() as f:
    genes=list(csv.DictReader(f,delimiter='\t'))
wb=openpyxl.load_workbook(P/'CAM40408-S4.xlsx',read_only=True,data_only=False,keep_links=False)
raw=list(wb.worksheets[0].values)[1:]
wb.close()
require('raw HRP row count',len(raw)==912)
for row in wells:
    if row['normalization']!='mean_background_mean_NT':
        continue
    plate=[r for r in raw if r[0]==row['plate'] and str(r[5])==row['repeat']]
    bg=[r for r in plate if r[2]=='No_cell_control']
    nt=[r for r in plate if r[2].startswith('ON-TARGETplus')]
    r=[r for r in plate if r[2]==row['gene']][0]
    for ix,endpoint in [(3,'CL_fold'),(4,'SN_fold')]:
        b=sum(x[ix] for x in bg)/len(bg)
        c=sum(x[ix] for x in nt)/len(nt)
        expected=(r[ix]-b)/(c-b)
        if row['valid_positive']=='True':
            require('HRP '+row['gene']+row['repeat']+endpoint,math.isclose(float(row[endpoint]),expected,rel_tol=1e-12))
variants=defaultdict(dict)
for x in wells:
    if x['valid_positive']=='True':
        variants[x['gene']].setdefault(x['normalization'],[]).append(x)
sensitivity={}
for gene in ['ACSL5','ERVFRD-1','FCF1','PEX2','GPR161','TMEM220','FAM98B','FAM102B','MXRA7']:
    result={}
    for mode,rows in variants[gene].items():
        result[mode]={'SN':[float(x['SN_fold']) for x in rows],'CL':[float(x['CL_fold']) for x in rows],'SN_CL':[float(x['SN_over_CL_fold']) for x in rows]}
    sensitivity[gene]=result
require('main gains exact',sorted(g['gene'] for g in genes if g['gain_rule']=='True')==['ACSL5','ERVFRD-1','FCF1','PEX2'])
require('robust gains exact',sorted(g['gene'] for g in genes if g['gain_robust_to_NT_and_background']=='True')==['ACSL5','ERVFRD-1','FCF1'])
# Unknown covariance sensitivity, explicitly not an identified confidence interval.
interaction=j['cross_cargo']['surface']
terms=[]
for cargo in ['PMP22','KCNQ1']:
    terms.extend(j['counter_screen'][cargo]['surface']['variance_terms'])
worst_se=sum(math.sqrt(x) for x in terms)
# This bound illustrates how unidentified covariance affects variance; no coverage claim.
covariance={'log2_effect':interaction['effect'],'sum_of_standard_errors_bound':worst_se,'effect_plus_minus_1_96_bound':[interaction['effect']-1.96*worst_se,interaction['effect']+1.96*worst_se],'interpretation':'Sensitivity envelope only, not a valid small-n confidence interval. Unknown correlations can remove the apparent interaction exclusion of zero.'}
counts={}
expected={'WT':(56,34),'G179S':(52,15),'G189E':(47,30),'V207M':(56,46)}
for r in j['function_descriptive']:
    obs=(r['DMSO']['n_cells'],r['VU0494372']['n_cells'])
    counts[r['variant']]={'native_n':list(obs),'supplement_table2_n':list(expected[r['variant']]),'matches':obs==expected[r['variant']]}
result={'valid':all(x['passed'] for x in checks),'checks':checks,'n_checks':len(checks),'sensitivity':sensitivity,'cargo_interaction_covariance_sensitivity':covariance,'electrophysiology_count_discrepancies':counts,'no_inferred_row_pairing':True,'not_independent_biological_replication':True}
(OUT/'independent-checks.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps({'valid':result['valid'],'n_checks':len(checks),'sensitivities':sensitivity,'counts':counts,'covariance':covariance},indent=2))
