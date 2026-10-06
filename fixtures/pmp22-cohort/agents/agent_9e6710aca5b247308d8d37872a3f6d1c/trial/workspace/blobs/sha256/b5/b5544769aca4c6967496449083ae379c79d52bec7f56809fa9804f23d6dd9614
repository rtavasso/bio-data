"""Make reporting values source-driven; retain superseded interpretation revisions."""
from pathlib import Path
import json
Q=Path(__file__).resolve().parents[1];O=Q/'outputs';U=O/'upstream'
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False))
s=json.loads((U/'antioxidant-posthoc-summary.json').read_text());lookup={(r['study'],r['panel']):r for r in s['panels']};nums=dict(eligible4={g:lookup[g,'eligible4'] for g in ['Nae1KO','TSC1KO','PTENKO','RaptorKO']},without_Nqo1={g:lookup[g,'discovery_gene_excluded'] for g in ['Nae1KO','TSC1KO','PTENKO','RaptorKO']},pmp22={g:lookup[g,'Pmp22']['effect'] for g in ['Nae1KO','TSC1KO','PTENKO','RaptorKO']},shared=s['broad']['shared'])
dump(U/'reported-numbers.json',nums)
for fn,newrev in [('mechanisms',21),('investigations',28),('discoveries',8)]:
 x=json.loads((O/(fn+'.json')).read_text());assert x['revision']==newrev-1;x['revision']=newrev
 if fn=='mechanisms':
  e=next(r for r in x['edges'] if r['id']=='nae1-antioxidant-signature');e['evidence'][0]['basis']=f"Eligible4 mean {lookup['Nae1KO','eligible4']['effect']:.6f}; without Nqo1 {lookup['Nae1KO','discovery_gene_excluded']['effect']:.6f}. Original five-gene lock untestable; retrospective subset is not validation."
  x['changes'].append(dict(reason='Independent source-to-output verification corrected hand-transcribed comparator effect values in the reporting layer; computed tables and inference dispositions unchanged. Authoritative values now programmatically extracted.',evidence=[dict(source='outputs/upstream/reported-numbers.json',locator='eligible4,without_Nqo1,pmp22,shared',basis='Exact values from executed JSON, not manual transcription')]))
 elif fn=='investigations':
  r=next(r for r in x['items'] if r['id']=='nae1-antioxidant-alternative');r['finding']='Five-gene lock untestable. Exploratory eligible4 effects: '+', '.join(f'{g}={lookup[g,"eligible4"]["effect"]:.6f}' for g in ['Nae1KO','TSC1KO','PTENKO','RaptorKO'])+'. Pmp22 declines in each. Corrects hand-transcribed reporting only; computed source outputs unchanged.'
  r=next(r for r in x['items'] if r['id']=='hormonal-metabolic-coverage');r.update(status='analyzed',finding='LXR/NAC and oxidative-stress-context sources audited, not a new independent human intervention analysis.',limitation='Published adult/developmental and rat-cell context distinctions; direct human hormonal generalization remains unfinished. No current time restriction.',next_action='Promote only when matched human promoter/protein outcomes with independent donors are available.',blocker_evidence=['inputs/upstream/PMC5802790.xml','inputs/upstream/PMC13360480.xml'])
  x['reporting_correction']='Final numeric digest generated from executed summaries after independent verification; superseded r027 retained.'
 else:x['reporting_correction']='Source-driven comparator numeric digest in outputs/upstream/reported-numbers.json; unchanged rejection/untestable/provisional candidate dispositions.'
 for p in [O/f'{fn}.r{newrev:03d}.json',O/(fn+'.json')]:dump(p,x)
report=(U/'REPORT.md').read_text()
for g,label in [('Nae1KO','Nae1 loss'),('TSC1KO','TSC1 loss'),('PTENKO','PTEN loss'),('RaptorKO','Raptor loss')]:
 r=lookup[g,'eligible4'];line=next(l for l in report.splitlines() if l.startswith('    '+label))
 for value in [r['effect'],*r['ci95'],lookup[g,'Pmp22']['effect']]:assert f'{value:.3f}' in line,(g,value,line)
assert f"{s['broad']['shared']:,}" in report
print('Reporting values verified against outputs; revisions 21/28/8 preserved.')
