"""Read schema and QC descriptions needed for the quantitative screen."""
import json
from pathlib import Path
q=Path(__file__).resolve().parents[1]
d=json.loads((q/'inputs/http/idr-file-meta-r001.payload').read_text())
print('IDR METADATA',json.dumps({k:d.get(k) for k in ['accession','submitter_comment','description','aliases','file_format_specifications','derived_from','assembly','biological_replicates','controlled_by','analysis_step_version','output_type']},indent=2))
sup=json.loads((q/'inputs/views/supplement-tables.json').read_text())
for fname in ['41586_2020_2077_MOESM7_ESM.xlsx','41586_2020_2077_MOESM11_ESM.xlsx','41586_2020_2077_MOESM12_ESM.xlsx']:
    for sheet,rows in sup[fname].items():
        print('QC',fname,sheet,'HEADERS',repr(rows[:5])[:7000])
