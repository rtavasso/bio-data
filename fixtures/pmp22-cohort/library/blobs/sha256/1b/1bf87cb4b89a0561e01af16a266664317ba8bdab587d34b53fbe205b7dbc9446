"""Inspect native processed supplements only; never evaluate workbook formulas."""
import hashlib
import json
from pathlib import Path
import zipfile
import openpyxl

Q = Path(__file__).resolve().parents[1]
p = Q / 'inputs/Fledrich2018-supplements.zip'
records = []
with zipfile.ZipFile(p) as z:
    assert z.testzip() is None
    for info in z.infolist():
        records.append({'member': info.filename, 'bytes': info.file_size})
        print(info.filename, info.file_size)
        if info.filename.endswith('.xlsx'):
            b = z.read(info)
            name = Path(info.filename).name
            dest = Q / 'inputs' / name
            assert not dest.exists()
            dest.write_bytes(b)
            records[-1]['sha256'] = hashlib.sha256(b).hexdigest()
            wb = openpyxl.load_workbook(dest, read_only=True, data_only=False)
            print('WORKBOOK', name, wb.sheetnames)
            for sheet in wb:
                print('SHEET', sheet.title, sheet.max_row, sheet.max_column)
                for row in list(sheet.iter_rows(min_row=1, max_row=8, values_only=True)):
                    print(row[:18])
(Q / 'outputs/supplement-inventory.json').write_text(json.dumps(records, indent=2))
