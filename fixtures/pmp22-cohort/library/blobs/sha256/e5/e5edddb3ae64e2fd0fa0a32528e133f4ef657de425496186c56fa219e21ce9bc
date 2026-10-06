"""Batch-normalized sensitivity of the complete planned PMP22 screen, not independent replication."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
out=q/'outputs/batch-r001'
out.mkdir(exist_ok=True)
selection=json.loads((q/'inputs/selection-r001.json').read_text())
primary=q/'outputs/screen-r001/binding-by-perturbation.json'
rows=json.loads(primary.read_text())
inputs=[]
universes={}
backgrounds=[]
for row in rows:
    choices=[r for r in selection if r['role']=='de_batch' and r['rbp']==row['rbp'] and r['cell']==row['cell']]
    if not choices:
        row['batch_status']='no_matched_perturbation'
        continue
    item=choices[0]
    label='file-'+item['file']['File accession']+'-r001'
    receipt=json.loads((q/'inputs/http'/(label+'.receipt.json')).read_text())
    sha=receipt['sha256']
    b=(w/'blobs/sha256'/sha[:2]/sha).read_bytes()
    assert receipt['complete'] and receipt['status']==200 and hashlib.sha256(b).hexdigest()==sha
    inputs.append({'name':label,'sha256':sha,'bytes':len(b),'source_url':receipt['url']})
    native=list(csv.reader(io.StringIO(b.decode()),delimiter='\t'))
    assert native[0]==['baseMean','log2FoldChange','lfcSE','stat','pvalue','padj']
    d={r[0]:{k:None if v=='NA' else float(v) for k,v in zip(native[0],r[1:],strict=True)} for r in native[1:]}
    assert len(d)==len(native)-1
    universe=sorted(d)
    usha=hashlib.sha256('\n'.join(universe).encode()).hexdigest()
    universes[usha]=universe
    backgrounds.append({'file':item['file']['File accession'],'rows':len(d),'gene_universe':usha,'finite_pvalue':sum(v['pvalue'] is not None for v in d.values()),'finite_padj':sum(v['padj'] is not None for v in d.values())})
    row['batch_file']=item['file']['File accession']
    if row['target_gene_id'] not in d:
        row['batch_status']='target_not_in_batch_selected_universe'
        continue
    row['batch_status']='measured'
    row.update({'batch_'+k:v for k,v in d[row['target_gene_id']].items()})
    row['batch_ci95_lower']=row['batch_log2FoldChange']-1.959963984540054*row['batch_lfcSE']
    row['batch_ci95_upper']=row['batch_log2FoldChange']+1.959963984540054*row['batch_lfcSE']
    row['batch_target_rna_depletion']={gid:d.get(gid) for gid in row['kd_target_gene_ids']}
paired=[r for r in rows if 'de_file' in r]
ps=[r.get('batch_pvalue') if r.get('batch_pvalue') is not None and r['control_matches'] else 1 for r in paired]
order=sorted(range(len(ps)),key=lambda i:ps[i])
last=1
for rank in range(len(ps),0,-1):
    i=order[rank-1]
    last=min(last,ps[i]*len(ps)/rank)
    paired[i]['batch_bh203']=last
    paired[i]['batch_by203']=min(1,last*sum(1/j for j in range(1,len(ps)+1)))
for r in paired:
    r['batch_response_pass']=bool(r.get('batch_padj') is not None and r['batch_padj']<=.05 and r['batch_bh203']<=.05)
    r['batch_direction_agrees']=bool(r.get('batch_log2FoldChange') is not None and r.get('pmp22_log2FoldChange') is not None and r['batch_log2FoldChange']*r['pmp22_log2FoldChange']>0)
summary={'rows':len(rows),'paired_contexts':len(paired),'batch_response_pass_count':sum(r['batch_response_pass'] for r in paired),'bound_batch_response_pass_count':sum(bool(r['pmp22_idr_peak_rows']) and r['batch_response_pass'] for r in paired),'batch_universe_count':len(universes),'binding_followups':[{k:r.get(k) for k in ['rbp','cell','pmp22_log2FoldChange','batch_log2FoldChange','batch_ci95_lower','batch_ci95_upper','batch_pvalue','batch_padj','batch_bh203','batch_direction_agrees','batch_target_rna_depletion']} for r in rows if r['pmp22_idr_peak_rows']],'not_independent':True}
for name,obj in [('summary.json',summary),('binding-by-perturbation-with-batch.json',rows),('batch-backgrounds.json',{'files':backgrounds,'universes':universes}),('input-manifest.json',{'native_inputs':inputs,'primary_table_sha256':hashlib.sha256(primary.read_bytes()).hexdigest(),'primary_manifest_sha256':hashlib.sha256((q/'inputs/screen-manifest-r001.json').read_bytes()).hexdigest()})]:
    (out/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
fields=list(dict.fromkeys(k for r in rows for k in r))
with (out/'binding-by-perturbation-with-batch.tsv').open('w') as f:
    wr=csv.DictWriter(f,fieldnames=fields,delimiter='\t')
    wr.writeheader()
    for r in rows:
        wr.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()})
print(json.dumps(summary,indent=2))
assert len(paired)==203
assert all(math.isfinite(p) and 0<=p<=1 for p in ps)
