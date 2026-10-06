import json
from pathlib import Path
import openpyxl
p=Path(__file__).resolve().parents[1]
w=openpyxl.load_workbook(p/'inputs/public/CAM40408-S6.xlsx',read_only=True,data_only=False,keep_links=False)
rows=list(w.worksheets[0].iter_rows(values_only=True))[1:]
bad=[{'source_row':i+2,'values':r} for i,r in enumerate(rows) if not all(isinstance(x, (int, float)) for x in r[3:6]) or r[3] != r[4]+r[5]]
print(json.dumps({'rows':len(rows),'bad':bad},indent=2))
(p/'outputs/golgi-count-audit.json').write_text(json.dumps({'rows':len(rows),'bad':bad},indent=2))
w.close()
