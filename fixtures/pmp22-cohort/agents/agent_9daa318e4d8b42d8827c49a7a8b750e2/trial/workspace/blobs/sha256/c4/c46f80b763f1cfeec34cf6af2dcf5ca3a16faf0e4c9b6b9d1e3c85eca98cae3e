import pathlib,json,csv,hashlib
import pandas as pd
q=pathlib.Path(__file__).resolve().parents[1]
m=json.loads((q/'inputs/artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a.json').read_text())
s=json.loads((q/'inputs/asset_5de0f13aed91ff279c9633dbded6a267.json').read_text())
rows=list(csv.DictReader(open(s['path']),delimiter='\t'))
d=pd.read_parquet(m['path'])
assert len(rows)==len(d)
for i,(r,p) in enumerate(zip(rows,d.to_dict('records')),2):
 assert p['__source_row']==i
 assert all(p[k]==v for k,v in r.items())
assert hashlib.sha256(pathlib.Path(m['path']).read_bytes()).hexdigest()==m['output_blob']
out={'source_rows_equal':len(rows),'prepared_hash_verified':m['output_blob'],'all_original_strings_and_row_locators_equal':True}
(q/'outputs/reuse-validation.json').write_text(json.dumps(out,indent=2))
print(out)
