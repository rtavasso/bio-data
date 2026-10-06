"""Summarize robustness; perform explicitly retrospective core-panel sensitivity and novelty text audit."""
import csv,hashlib,json,os,re
from pathlib import Path
import numpy as np
from defusedxml import ElementTree as ET
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';O=Q/'outputs';core=['Mpz','Mbp','Mag','Prx','Mal']
rows=[]
for stage in ['screen','array','validation']:
    summary=json.loads((O/f'{stage}-summary.json').read_text());sens=list(csv.DictReader((O/f'{stage}-sensitivities.tsv').open(),delimiter='\t'))
    genes=list(csv.DictReader((O/f'{stage}-gene-effects.tsv').open(),delimiter='\t'))
    for r in summary['contrasts']:
        data=r.get('dataset',summary.get('dataset'));name=r['contrast'];ss=[s for s in sens if s['contrast']==name and (not s.get('dataset') or s['dataset']==data)]
        by={g['gene']:float(g['effect']) for g in genes if g['contrast']==name and (not g.get('dataset') or g['dataset']==data)}
        value=by['Pmp22']-float(np.mean([by[g] for g in core])) if all(g in by for g in ['Pmp22',*core]) else None
        rr={'dataset':data,'contrast':name,'stage':stage,'posthoc_core5_effect':value,'core5':['Mpz','Mbp','Mag','Prx','Mal'],'reason':'Retrospective exclusion of relatively preserved Cnp/Plp1 after full-panel outcomes; descriptive comparator-dependence check, NEVER replaces frozen myelin7 test','target_vs_each_myelin':r.get('target_vs_each_myelin',{})}
        for kind in sorted(set(s['kind'] for s in ss)):
            vals=[float(s['effect']) for s in ss if s['kind']==kind];rr[kind+'_range']=[min(vals),max(vals)]
        rows.append(rr)
        print(data,name,'core5',value,{k:v for k,v in rr.items() if k.endswith('_range')})
(O/'robustness-and-core5.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
paths={'GSE177037':Q.parent/'q_ec00fef1019a4c6f/inputs/public/repair.xml','GSE104324':Q/'inputs/primary/PMC5960709.xml','GSE163132':Q/'inputs/primary/PMC9469140.xml','E-MEXP-3491':Q/'inputs/public/PMC3669361.xml','GSE108231':Q/'inputs/public/PMC5956991.xml'}
audit={}
for ds,p in paths.items():
    root=ET.parse(p).getroot();hits=[]
    for i,el in enumerate(root.iter('p')):
        s=' '.join(el.itertext())
        if re.search(r'\bPmp22\b|peripheral myelin protein 22',s,re.I):hits.append({'paragraph_index':i,'attributes':el.attrib,'text':s})
    audit[ds]={'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pmp22_paragraphs':hits,'scope':'main XML paragraph text; not exhaustive supplements or literature; absence is not novelty'}
    print('NOVELTY_TEXT_AUDIT',ds,'paragraphs',len(hits))
    for h in hits:print(h['paragraph_index'],h['text'][:1800])
(O/'novelty-text-audit.json').write_text(json.dumps(audit,indent=2))
x=json.loads((O/'promoter-peer-answer.json').read_text());(O/'promoter-peer-answer.md').write_text(x['content']['body']);print('PROMOTER_PEER',x['content']['body'])
