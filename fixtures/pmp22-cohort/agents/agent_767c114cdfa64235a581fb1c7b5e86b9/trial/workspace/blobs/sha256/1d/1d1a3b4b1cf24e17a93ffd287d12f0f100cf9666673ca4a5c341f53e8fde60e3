"""Inspect native supplemental tables without evaluating formulas or serialized code."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
import openpyxl

q = Path(__file__).resolve().parents[1]
out = q / 'outputs/independent-probe-r001.json'
reports = []
for label in ['pum-bruchase-supp-r001', 'pum-cnot-supp-r001', 'pum-tcam-supp-r001']:
    payload = q / 'inputs/http' / (label + '.payload')
    receipt = json.loads(payload.with_suffix('.receipt.json').read_text())
    assert receipt['status'] == 200 and receipt['complete']
    assert hashlib.sha256(payload.read_bytes()).hexdigest() == receipt['sha256']
    archive = zipfile.ZipFile(payload)
    report = {'source': label, 'sha256': receipt['sha256'], 'members': [], 'tables': []}
    for name in archive.namelist():
        info = archive.getinfo(name)
        report['members'].append({'name': name, 'uncompressed_bytes': info.file_size})
        if name.endswith('.tsv'):
            rows = list(csv.reader(io.StringIO(archive.read(name).decode()), delimiter='\t'))
            report['tables'].append({'name': name, 'rows_including_header': len(rows), 'header': rows[:2], 'pmp22': [r for r in rows if 'PMP22' in r], 'controls': [r for r in rows if any(g in r for g in ['PUM1', 'PUM2', 'CCNG2'])]})
        elif name.endswith('.xlsx'):
            wb = openpyxl.load_workbook(io.BytesIO(archive.read(name)), read_only=True, data_only=False)
            for sheet in wb:
                sheet.reset_dimensions()
                count = 0
                first = []
                targets = []
                for row in sheet.iter_rows(values_only=True):
                    if not any(v is not None for v in row):
                        continue
                    count += 1
                    if len(first) < 6:
                        first.append(row[:30])
                    if any(str(v).upper() in ['PMP22', 'PUM1', 'PUM2', 'NM_000304', 'NM_153321'] for v in row):
                        targets.append(row)
                report['tables'].append({'name': name, 'sheet': sheet.title, 'nonempty_rows': count, 'first_rows': first, 'targets': targets})
            wb.close()
    reports.append(report)
out.write_text(json.dumps(reports, indent=2, allow_nan=False))
for r in reports:
    print('SOURCE', r['source'], 'MEMBERS', [(m['name'], m['uncompressed_bytes']) for m in r['members'] if not m['name'].endswith(('.jpg','.gif'))])
    for t in r['tables']:
        print(json.dumps(t, allow_nan=False))
