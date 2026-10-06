"""Summarize preserved literature discovery and experiment QC without treating it as proof."""
import json
from pathlib import Path
q=Path(__file__).resolve().parents[1]
for label in ['novelty-PUM','novelty-QKI','novelty-other','independent-PUM','independent-QKI']:
    obj=json.loads((q/'inputs/http'/(label+'-r001.payload')).read_text())
    records=obj['resultList']['result']
    print('\nSEARCH',label,'TOTAL',obj['hitCount'],'RETURNED',len(records))
    simple=[]
    for r in records:
        simple.append({k:r.get(k) for k in ['id','pmcid','title','pubYear','doi','abstractText']})
        title=r.get('title','')
        # Show all novelty-PUM results and biologically relevant titles, not only supportive claims.
        if label=='novelty-PUM' or any(x in title.lower() for x in ['pumilio','pum1','pum2','quaking','qki','schwann','peripheral','post-transcriptional','posttranscriptional']):
            print(r['id'],r.get('pmcid'),r.get('pubYear'),title)
            if label=='independent-PUM':
                print(r.get('abstractText','')[:1800])
    (q/'inputs/views'/(label+'-results.json')).write_text(json.dumps(simple,indent=2))
for rbp in ['PUM2','QKI']:
    d=json.loads((q/'inputs/http'/(rbp+'-kd-experiment-r001.payload')).read_text())
    print('KD EXPERIMENT',rbp,d.get('accession'),d.get('description'),d.get('target'), 'AUDIT',json.dumps(d.get('audit',{}))[:2500])
    for rep in d.get('replicates',[]):
        lib=rep.get('library',{})
        bio=lib.get('biosample',{})
        print('REPLICATE',rep.get('biological_replicate_number'),{k:bio.get(k) for k in ['accession','description','treatments','applied_modifications','characterizations','documents']})
    (q/'inputs/views'/(rbp+'-replicates.json')).write_text(json.dumps(d.get('replicates',[]),indent=2))
