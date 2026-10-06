"""Inspect measured binders and search independent resources before validation acquisition."""
from collections import Counter
import json
from pathlib import Path
import statistics
import subprocess
from urllib.parse import urlencode
from retrieve import retrieve
q=Path(__file__).resolve().parents[1]
rows=json.loads((q/'outputs/screen-r001/binding-by-perturbation.json').read_text())
bound=[r for r in rows if r['pmp22_idr_peak_rows']]
(q/'outputs/binding-followups.json').write_text(json.dumps(bound,indent=2))
print('BINDERS',json.dumps(bound,indent=2))
paired=[r for r in rows if r.get('pmp22_pvalue') is not None]
print('BEST RNA ONLY',json.dumps([{k:r.get(k) for k in ['rbp','cell','pmp22_baseMean','pmp22_log2FoldChange','pmp22_padj','pmp22_screen_bh203','adequate_target_rna_depletion']} for r in sorted(paired,key=lambda r:r['pmp22_pvalue'])[:10]],indent=2))
for cell in ['HepG2','K562']:
    rs=[r for r in paired if r['cell']==cell]
    vals=[r['pmp22_baseMean'] for r in rs]
    print('COVERAGE',cell,'range',min(vals),max(vals),'median',statistics.median(vals),'low20',sum(v<20 for v in vals),'adequateKD',sum(r['adequate_target_rna_depletion'] for r in rs))
for name in ['PUM2','QKI','TIA1','SND1','IGF2BP2']:
    result=subprocess.run(['./bin/bio','community','search','--text',name,'--limit','100'],capture_output=True,text=True,check=True)
    (q/'inputs/community'/('candidate-'+name+'.json')).write_text(result.stdout)
    d=json.loads(result.stdout)
    print('FORUM',name,d['total'],[(i['subject'],i['title']) for i in d['items']])
queries={
'novelty-PUM':'PMP22 AND (PUM1 OR PUM2 OR Pumilio)',
'novelty-QKI':'PMP22 AND (QKI OR quaking)',
'novelty-other':'PMP22 AND (TIA1 OR TIA-1 OR SND1 OR IGF2BP2)',
'independent-PUM':'(PUM1 OR PUM2) AND (RNA-seq OR RNAseq OR transcriptome) AND (knockdown OR knockout)',
'independent-QKI':'QKI AND Schwann AND (RNA-seq OR transcriptome)'}
for label,query in queries.items():
    retrieve(label+'-r001','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':query,'format':'json','pageSize':100,'resultType':'core'}))
for row in bound:
    if row['rbp'] in ['PUM2','QKI']:
        retrieve(row['rbp']+'-kd-experiment-r001','https://www.encodeproject.org/'+row['rna_experiment']+'/?format=json')
