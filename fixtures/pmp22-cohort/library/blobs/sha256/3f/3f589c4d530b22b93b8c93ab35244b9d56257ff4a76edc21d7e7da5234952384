"""Audit annotation correspondence without comparing expression values."""
import csv,json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';p=q/'inputs/public'
x=json.loads((p/'raptor-paper-metadata.json').read_text());assert x['hitCount']==1;a=x['resultList']['result'][0];print('RAPTOR_PAPER',a['title'],a.get('pmcid'),a.get('doi'))
if a.get('pmcid'):(q/'inputs/raptor-fulltext-url.json').write_text(json.dumps({a['pmcid']+'.xml':'https://www.ebi.ac.uk/europepmc/webservices/rest/'+a['pmcid']+'/fullTextXML'},indent=2))
with (p/'E-MEXP-3491.matrix.txt').open() as f:
    rr=csv.reader(f,delimiter='\t');next(rr);next(rr);names=[r[0] for r in rr]
with (p/'Schwanncellscontrol1-annotation-only.txt').open() as f:
    for line in f:
        if line.startswith('FEATURES'):keys=line.rstrip('\n').split('\t');break
    native=[dict(zip(keys,r)) for r in csv.reader(f,delimiter='\t') if r and r[0]=='DATA']
print('ROW_COUNTS',len(names),len(native))
bad=[(i,names[i],d['GeneName'],d['SystematicName'],d['ProbeName']) for i,d in enumerate(native) if i>=len(names) or names[i]!=d['GeneName']]
print('NAME_MISMATCHES',len(bad),bad[:25])
wanted=['Pmp22',*sum(json.loads((q/'inputs/panel-spec.json').read_text())['panels'].values(),[])]
for g in wanted:
    print(g,'MATRIX_ROWS',[i for i,s in enumerate(names) if s==g],'NATIVE_ROWS',[(i,d['ProbeName'],names[i]) for i,d in enumerate(native) if d['GeneName']==g])
(q/'outputs/array-annotation-correspondence.json').write_text(json.dumps({'matrix_rows':len(names),'native_rows':len(native),'mismatches':bad},indent=2))
