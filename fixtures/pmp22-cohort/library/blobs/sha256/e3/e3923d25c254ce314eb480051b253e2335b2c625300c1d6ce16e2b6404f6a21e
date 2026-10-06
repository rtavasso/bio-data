"""Select all source-defined high-quality eCLIP contexts and matched processed RNA contrasts."""
from collections import Counter
import json
from pathlib import Path
q=Path(__file__).resolve().parents[1]
sup=json.loads((q/'inputs/views/supplement-tables.json').read_text())
mat=sup['41586_2020_2077_MOESM4_ESM.xlsx']
eclip=[dict(zip(mat['eCLIP'][0],r)) for r in mat['eCLIP'][1:]]
kd=[dict(zip(mat['KD-RNA-seq'][0],r)) for r in mat['KD-RNA-seq'][1:]]
meta=json.loads((q/'inputs/publication-file-metadata.json').read_text())
byfile={r['File accession']:r for r in meta}
selection=[]
for e in eclip:
    f=byfile[e['Reproducible Peak Files']].copy()
    assert f['File format']=='bed narrowPeak' and f['Assembly']=='hg19'
    selection.append({'role':'idr_peaks','rbp':e['RBP'],'cell':e['Cell_line'],'experiment':e['eCLIP_exp'],'control':e['Control_exp'],'file':f})
    ks=[k for k in kd if k['RBP']==e['RBP'] and k['Cell_line']==e['Cell_line']]
    assert len(ks)<=1
    if not ks:
        continue
    k=ks[0]
    # Retain obsolete supplement IDs, but select current source-listed corrected DESeq2 files by exact experiment/control.
    for role,key in [('de_paired','RBP knockdown DESeq'),('de_batch','RBP knockdown DESeq after batch Correction')]:
        accession=k[key]
        collection='secondary' if role=='de_paired' else 'batch'
        matches=[r for r in meta if r['publication_collection']==collection and r['File dataset']==k['RNA-Seq_exp'] and r['File output type']=='differential expression quantifications' and 'DESeq' in r['Submitter comment']]
        assert len(matches)==1, (role,k['RNA-Seq_exp'],matches)
        f=matches[0]
        assert f['Biosample term name']==e['Cell_line'], (role,k,f)
        control_matches=f['Control dataset']==k['Control_exp']
        if not control_matches:
            print('CONTROL CONFLICT, RETAIN BUT DO NOT RANK',role,k['RNA-Seq_exp'],k['Control_exp'],f['Control dataset'])
        selection.append({'role':role,'rbp':e['RBP'],'cell':e['Cell_line'],'experiment':k['RNA-Seq_exp'],'control':k['Control_exp'],'supplement_file_id':accession,'control_matches':control_matches,'file':f})
print('COUNTS',Counter(x['role'] for x in selection),Counter((x['role'],x['cell']) for x in selection))
for role in ['de_paired','de_batch']:
    x=next(x for x in selection if x['role']==role)
    print('EXAMPLE',role,json.dumps(x,indent=2))
(q/'inputs/selection-r001.json').write_text(json.dumps(selection,indent=2))
(q/'inputs/source-assay-pairs.json').write_text(json.dumps({'eclip':eclip,'kd':kd},indent=2))
print('PRIMARY SUM_BYTES',sum(int(x['file']['Size']) for x in selection if x['role']!='de_batch'))
