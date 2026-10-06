"""Validate registered source locators against original saved bytes; report no effects."""
import hashlib
import io
import json
import math
import os
import zipfile
from pathlib import Path

import openpyxl

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
workspace = Path(os.environ['BIO_WORKSPACE'])
loc = json.loads((out / 'upstream-regulator-source-locators.json').read_text())
reg = json.loads((out / 'registration-upstream-locators.json').read_text())
back = json.loads((out / 'readback-upstream-locators.json').read_text())
receipt = json.loads((out / 'regulator-locator-execution-r001.json').read_text())
digest = hashlib.sha256((out / 'upstream-regulator-source-locators.json').read_bytes()).hexdigest()
assert reg['output_blob'] == back['output_blob'] == digest
assert back['id'] == reg['artifact'] and not reg['conflicting_outputs']
assert q.name in json.dumps(back['questions'])
assert receipt['exit_code'] == 0 and receipt['complete'] and receipt['code_unchanged']
assert receipt['outputs'][0]['sha256'] == digest
assert hashlib.sha256((q / 'scripts/locate_regulator_rows.py').read_bytes()).hexdigest() == receipt['code_sha256']
archive_digest = '61f3e98f581209f8385a6c4cdee8d1ea1c39b00da761911d8fdf89bb22da7ff1'
archive_path = workspace / 'blobs/sha256' / archive_digest[:2] / archive_digest
checks = []
with zipfile.ZipFile(archive_path) as archive:
    for wb in loc['workbooks']:
        raw = archive.read(wb['member'])
        assert hashlib.sha256(raw).hexdigest() == wb['member_sha256']
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
        for source_sheet in wb['sheets']:
            if source_sheet['sheet'].startswith('Control vs '):
                worksheet = book[source_sheet['sheet']]
                required = {item['row']: item for item in source_sheet['regulator_rows']}
                checked = []
                for index, row in enumerate(worksheet.iter_rows(), 1):
                    if index not in required:
                        continue
                    assert row[2].value == required[index]['symbol']
                    sample_cells = row[20:56]
                    assert all(c.data_type != 'f' and isinstance(c.value, (float, int))
                               and math.isfinite(c.value) for c in sample_cells)
                    checked.append({'symbol': row[2].value, 'row': index, 'sample_columns': 'U:BD', 'finite_numeric': True})
                assert len(checked) == 2
                checks.append({'sheet': worksheet.title, 'checked_rows': checked})
        if wb['member'] == 'elife-29241-fig4-data1.xlsx':
            rows = list(book['Tabelle1'].iter_rows())
            ages = []
            for row in rows[2:]:
                ages.append(row[0].value)
                assert all(c.data_type != 'f' and isinstance(c.value, (float, int))
                           and math.isfinite(c.value) for c in row[1:13])
            checks.append({'member': wb['member'], 'age_labels': ages, 'B3_M7_finite_numeric': True,
                           'same_animals_as_RNA_not_established': True})
        book.close()
result = {'artifact': reg['artifact'], 'artifact_readback_verified': True, 'producer_verified': True,
          'source_checks': checks, 'effects_computed': False, 'formulas_executed': False}
(out / 'upstream-regulator-locator-validation.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps(result))
