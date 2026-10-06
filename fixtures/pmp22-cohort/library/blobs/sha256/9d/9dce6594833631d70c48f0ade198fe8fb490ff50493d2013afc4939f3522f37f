"""Verify selected-pair versus gene-FDR coverage and exact splice-to-transcript mapping."""
import json
from pathlib import Path
from collections import Counter,defaultdict
Q=Path(__file__).resolve().parents[1]
o=json.loads((Q/'outputs/inspection-v11.json').read_text())
print('INITIAL significant pairs',Counter((r['assay'],r['tissue']) for r in o['significant_pairs']))
for t in ['Nerve_Tibial','Cells_Cultured_fibroblasts']:
    rows=[r for r in o['significant_pairs'] if r['assay']=='eqtl' and r['tissue']==t]
    if rows:print(t,'count',len(rows),'range',min(int(x['variant_id'].split('_')[1]) for x in rows),max(int(x['variant_id'].split('_')[1]) for x in rows),'min_p',min(x['pval_nominal'] for x in rows))
g=json.loads((Q/'inputs/text/pmp22-gencode47.json').read_text())['rows']
exons=defaultdict(list);transcripts={}
for r in g:
    if r['type']=='exon':exons[r['attributes']['transcript_id']].append(r)
    if r['type']=='transcript':transcripts[r['attributes']['transcript_id']]=r
for tx,ex in exons.items():
    ex=sorted(ex,key=lambda r:r['end1'],reverse=True)
    for i,(up,down) in enumerate(zip(ex,ex[1:])):
        if (down['end1'],up['start1'])==(15260761,15265154):
            print('JUNCTION MATCH',tx,'source_exon_ordinal',i+1,'target_exon_ordinal',i+2,'tx_end1',transcripts[tx]['end1'])
