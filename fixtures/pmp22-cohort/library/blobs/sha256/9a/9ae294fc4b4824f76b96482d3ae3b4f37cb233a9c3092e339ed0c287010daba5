"""Inspect preserved ENCORE source metadata; do not infer coverage from titles."""
import json
from pathlib import Path
q=Path(__file__).resolve().parents[1]
rows=[]
for name in ['eclip','hepg2','k562','secondary','batch']:
    p=q/'inputs/http'/f'encode-{name}-meta-r001.payload'
    obj=json.loads(p.read_text())
    print('\nSOURCE',name,obj.get('accession'),obj.get('description'), 'KEYS',list(obj))
    print('ARRAY SHAPES',[(key,len(obj.get(key,[])),str(obj.get(key,[])[:1])[:1200]) for key in ['files','original_files','related_files','contributing_files','documents','references']])
    for f in obj.get('files',[]):
        if isinstance(f,str):
            rows.append({'collection':obj['accession'],'file_ref':f})
            continue
        keep={k:f.get(k) for k in ['accession','status','file_format','file_format_type','file_size','output_type','assembly','genome_annotation','submitted_file_name','title','href','md5sum','description']}
        keep['collection']=obj['accession']
        rows.append(keep)
        print(json.dumps(keep))
(q/'inputs/encode-file-inventory.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
p=json.loads((q/'inputs/http/ePMC-paper-search-r001.payload').read_text())
print('PAPER',json.dumps(p))
# Briefly inspect reused baseline derivation without executing inherited code.
r=json.loads((q.parent/'q_a9976f21480c4fec/outputs/registrations-r003/rna-fate-audit.json.readback.json').read_text())
print('BASELINE DERIVATION',json.dumps(r.get('manifest',{}).get('derivation',{})))
print('SCHWANN LIBRARY',json.dumps([{k:x.get(k) for k in ['subject','title','summary']} for x in json.loads((q/'inputs/community/library-artifact-Schwann.json').read_text())['items']],indent=2))
