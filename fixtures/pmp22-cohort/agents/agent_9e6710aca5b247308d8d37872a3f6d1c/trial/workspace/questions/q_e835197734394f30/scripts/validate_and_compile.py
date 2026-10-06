"""Validate source-token extraction, build assay eligibility and archive manifest."""
import csv
import hashlib
import json
import math
from pathlib import Path

Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
def strict(path):
    def reject(x):
        raise ValueError(x)
    return json.loads(path.read_text(),parse_constant=reject)
summary=strict(OUT/'array-summary.json')
receipt=strict(OUT/'array-execution-r001.json')
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
assert sha(Path(receipt['producer']))==receipt['code_sha256']
for item in receipt['outputs']:
    assert sha(Path(item['path']))==item['sha256'] and item['written']
with (OUT/'array-all-probes.tsv').open() as f:
    rows=list(csv.DictReader(f,delimiter='\t'))
assert len(rows)==summary['n_measured_probes_each']
expected={}
for r in rows:
    for s in summary['sample_ids']:
        expected[int(r[s+'_line'])]=(r['probe'],r[s+'_value_token'],r[s+'_detection_token'])
source=Q.parents[1]/'blobs'/'sha256'/summary['source_blob'][:2]/summary['source_blob']
seen=0
platform_ids=[]
mode=False
with source.open() as f:
    for n,line in enumerate(f,1):
        fields=line.rstrip('\r\n').split('\t')
        if n in expected:
            assert tuple(fields)==expected[n],(n,fields,expected[n])
            seen+=1
        if fields[0]=='!platform_table_begin':
            mode=True
        elif fields[0]=='!platform_table_end':
            mode=False
        elif mode and fields[0] not in ('ID','!platform_table_begin'):
            platform_ids.append(fields[0])
assert seen==len(rows)*len(summary['sample_ids'])
measured={r['probe'] for r in rows}
platform_only=sorted(set(platform_ids)-measured)
for r in rows:
    for name,c in summary['contrasts'].items():
        a,b=float(r[c['case']+'_value']),float(r[c['control']+'_value'])
        assert math.isclose(float(r[name]),a-b,abs_tol=1e-12)
assert len(platform_ids)==summary['n_platform_probes']
assert summary['n_panel_probes']==len(summary['panel'])
assert len({r['probe'] for r in summary['panel']})==summary['n_panel_probes']
assert [r['probe'] for r in summary['panel'] if r['symbols']=='Pmp22']==['TC1000000824.rn.2']
curated=strict(Q/'inputs/curated-evidence.json')
fields=sorted({k for r in curated for k in r}|{'source_blob'})
for r in curated:
    p=Q/r['file']
    assert p.exists()
    r['source_blob']=sha(p)
with (OUT/'assay-eligibility.tsv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,delimiter='\t')
    w.writeheader()
    w.writerows(curated)
metadata=strict(OUT/'sample-metadata.json')
elig=[]
for r in metadata:
    m=r['metadata']
    series=r['series']
    reason={
        'GSE165206':'One array per condition; two-day total RNA; no donor variance, endogenous motif or nascent endpoint',
        'GSE147285':'Age/selection/compartment differences; no defined input or promoter endpoint; cells not donors',
        'GSE294160':'Age-specific pooled libraries; replicate labels not independent within-age donors; no controlled input or promoter endpoint',
        'GSE79115':'Paper Taz cKO;Yap cHet mixed nerve pools differs from deposit DBL-cKO sciatic labels; no stiffness/input factorial or promoter endpoint'
    }[series]
    elig.append({'series':series,'sample':r['sample'],'title':' | '.join(m.get('!Sample_title',[])),'characteristics':' | '.join(m.get('!Sample_characteristics_ch1',[])),'description':' | '.join(m.get('!Sample_description',[])),'source_file':r['source'],'source_line':r['line'],'source_blob':sha(Q/'inputs/primary'/r['source']),'eligible_direct_test':False,'reason':reason})
with (OUT/'sample-eligibility.tsv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(elig[0]),delimiter='\t')
    w.writeheader()
    w.writerows(elig)
validation={'array_source_records_verified':seen,'measured_probes':len(rows),'platform_only_not_measured_probes':platform_only,'panel_probes':len(summary['panel']),'sample_metadata_rows':len(metadata),'assay_contexts':len(curated),'qualifying_direct_test_contexts':sum(r['direct_test_eligible'] for r in curated),'all_registered_candidate_json_finite':True,'source_values_preserved':True,'contrasts_recalculated':True,'producer_receipt_checked':True,'not_independent_replication':True,'curation_is_agent_interpretation':True}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2,allow_nan=False)+'\n')
print(json.dumps(validation,indent=2))
