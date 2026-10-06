"""Summarize first executed screen and extract peer advice without source execution."""
import csv,json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'outputs/screen-summary.json').read_text())
s=list(csv.DictReader((q/'outputs/screen-sensitivities.tsv').open(),delimiter='\t'))
for r in x['contrasts']:
    rows=[z for z in s if z['dataset']==r['dataset'] and z['contrast']==r['contrast']]
    print(r['dataset'],r['contrast'])
    print('PANELS',{k:round(r[k]['effect'],4) for k in ['Pmp22','myelin7','identity4','proliferation6','stress6']})
    print('TARGET_VS_MARKERS',r['target_vs_each_myelin'])
    for kind in sorted(set(z['kind'] for z in rows)):
        v=[float(z['effect']) for z in rows if z['kind']==kind];print(kind,min(v),max(v))
    print('conditional permutation',r['conditional_exact_permutation_p'])
y=json.loads((q/'outputs/parent-answer.json').read_text()); (q/'outputs/parent-answer.md').write_text(y['content']['body']);print('\nPARENT_ANSWER\n',y['content']['body'])
