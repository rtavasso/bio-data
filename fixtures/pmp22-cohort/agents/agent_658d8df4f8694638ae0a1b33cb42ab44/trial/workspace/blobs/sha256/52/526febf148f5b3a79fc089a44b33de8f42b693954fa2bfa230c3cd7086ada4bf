import json
from pathlib import Path
import openpyxl
p=Path(__file__).resolve().parents[1]/'inputs/public/JCI201297-data-native.xlsx'
w=openpyxl.load_workbook(p, read_only=True, data_only=False, keep_links=False)
for name in ['Fig. 3A','Fig. 3B','Fig. 3C','Fig. 5B']:
    print(name)
    ws=w[name]
    for row in ws:
        vals={c.coordinate:c.value for c in row if c.value is not None and c.column <= 30}
        if vals:
            print(json.dumps(vals, default=str))
w.close()
