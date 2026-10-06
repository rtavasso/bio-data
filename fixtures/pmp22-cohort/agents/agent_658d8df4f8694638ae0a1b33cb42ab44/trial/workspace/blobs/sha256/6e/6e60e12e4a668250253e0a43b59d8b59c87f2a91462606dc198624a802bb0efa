"""Safe native workbook inventory and value dump; no formulas are executed."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
import openpyxl
ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'inputs/public'
parser = argparse.ArgumentParser()
parser.add_argument('--unpack-uggt', action='store_true')
args = parser.parse_args()
if args.unpack_uggt:
    rows = []
    with zipfile.ZipFile(P/'PMC7771966-supplements.zip') as z:
        for info in z.infolist():
            if info.filename.endswith(('.xlsx','.csv')):
                assert '/' not in info.filename and info.file_size < 50_000_000
                body = z.read(info)
                target = P / info.filename
                if target.exists():
                    assert target.read_bytes() == body
                else:
                    target.write_bytes(body)
                rows.append({'member': info.filename, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()})
    (P/'UGGT-extraction.json').write_text(json.dumps(rows, indent=2))
manifest = []
for path in sorted(P.glob('*.xlsx')):
    if not zipfile.is_zipfile(path):
        continue
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
    data = []
    details = []
    for sheet in wb:
        cells = [{'row': number, 'values': {cell.column_letter: cell.value for cell in row if cell.value is not None}} for number, row in enumerate(sheet, 1) if any(cell.value is not None for cell in row)]
        data.append({'sheet': sheet.title, 'rows': cells})
        details.append({'sheet': sheet.title, 'rows': sheet.max_row, 'cols': sheet.max_column})
        print(path.name, sheet.title, sheet.max_row, sheet.max_column)
        for item in cells[:5]:
            print(json.dumps(item, default=str))
    wb.close()
    (P/(path.name+'.values.json')).write_text(json.dumps(data, indent=2, default=str))
    manifest.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sheets': details})
(P/'workbook-inventory.json').write_text(json.dumps(manifest, indent=2))
