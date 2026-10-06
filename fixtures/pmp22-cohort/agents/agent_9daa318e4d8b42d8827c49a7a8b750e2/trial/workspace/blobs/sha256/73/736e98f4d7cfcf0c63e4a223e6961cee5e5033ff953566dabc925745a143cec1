import csv,json,pathlib,gzip
q=pathlib.Path(__file__).resolve().parents[1]
def info(a):return json.loads((q/'inputs'/f'{a}.json').read_text())
ref=info('asset_c3bc524f6b0d57c01d1709dec24cf801')
genes={'Pmp22','Egr2','Jun','Mtor','Sox10','Tead1','Yap1','Wwtr1'}
prom=[]
for i,r in enumerate(csv.reader(open(ref['path']),delimiter='\t'),1):
 if r[12] in genes:
  tss=int(r[4]) if r[3]=='+' else int(r[5])
  lo,hi=(tss-1500,tss+500) if r[3]=='+' else (tss-500,tss+1500)
  prom.append({'gene':r[12],'transcript':r[1],'chr':r[2],'strand':r[3],'tss':tss,'start':max(0,lo),'end':hi,'ref_source_row':i})
samples={'GFP1':'asset_5d646466456220a089ff8e65ff2dd2a6','GFP2':'asset_5af4bd06c28c3f88d7b4cde500f161bd','AS1':'asset_dbbd6e785b9997688f2be7d6ace37d76','AS2':'asset_b59cf55f51237ff92b69d16a70bdb77d'}
hits=[]; totals={}
for sample,a in samples.items():
 p=info(a)['path']
 opener=gzip.open if sample!='GFP1' else open
 with opener(p,'rt') as f:
  n=0
  for i,r in enumerate(csv.reader(f,delimiter='\t'),1):
   n+=1
   for g in prom:
    if r[0]==g['chr'] and int(r[1])<g['end'] and int(r[2])>g['start']:
     hits.append(dict(g,sample=sample,asset=a,peak_source_row=i,peak_start=int(r[1]),peak_end=int(r[2]),peak_name=r[3],signalValue=r[6],overlap_bp=min(int(r[2]),g['end'])-max(int(r[1]),g['start'])))
  totals[sample]=n
with open(q/'outputs/atac-promoter-overlaps.tsv','w') as f:
 w=csv.DictWriter(f,fieldnames=list(hits[0]),delimiter='\t');w.writeheader();w.writerows(hits)
summary=[]
for g in prom:
 summary.append(dict(g,**{s:sum(h['sample']==s and h['transcript']==g['transcript'] for h in hits) for s in samples}))
with open(q/'outputs/atac-promoter-summary.tsv','w') as f:
 w=csv.DictWriter(f,fieldnames=list(summary[0]),delimiter='\t');w.writeheader();w.writerows(summary)
(q/'outputs/atac-method.json').write_text(json.dumps({'assembly':'rn6, sourced from reference parent URL and GSE201627 methods','window':'strand-aware -1500/+500 bp around RefSeq transcript TSS; 0-based half-open','peak_totals':totals,'limitations':'Called-peak overlap is not differential accessibility. Peak absence is selected-out, not measured-zero. signalValue is not compared across libraries. Reference downloaded 2026 may differ from original author reference; P1/P2 assignment not assumed. Duplicate transcript promoter windows retained, not independent evidence.'},indent=2))
print(json.dumps(summary,indent=2))
