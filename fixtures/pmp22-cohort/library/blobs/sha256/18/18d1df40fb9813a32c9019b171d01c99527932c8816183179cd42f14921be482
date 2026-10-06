"""Inspect saved source locators only; do not compute candidate effects or execute formulas."""
import csv
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

q = Path(__file__).resolve().parents[1]
workspace = Path(os.environ['BIO_WORKSPACE'])

def blob_path(digest):
    path = workspace / 'blobs' / 'sha256' / digest[:2] / digest
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == digest
    return path

out = {'scope': 'Source/header/feature-location inspection only; expression values and effect estimates intentionally not exported',
       'formula_policy': 'Read workbook XML through openpyxl with data_only=False; never execute formulas or macros',
       'tsv': [], 'workbooks': []}
for name, digest in [
    ('nae1-all-expected-counts.tsv', '2d6f0b558d32cd63d89f9799882ed9cb084400aca6cd3b000b5cfdd2cf91673a'),
    ('nae1-all-log2normalized.tsv', '6474b5abdfc1cddbc1c893b16115ec092382f9eb18555afc9bfe0245b1286525'),
]:
    matches = []
    with blob_path(digest).open() as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        columns = reader.fieldnames
        assert columns is not None
        for line, row in enumerate(reader, 2):
            if row['symbol'] in {'Egr2', 'Sox10'}:
                matches.append({'symbol': row['symbol'], 'gene_id': row['gene_id'], 'line_including_header': line,
                                'complete_sample_fields': all(row[c] != '' for c in columns if c not in {'gene_id', 'symbol'})})
    assert sorted(x['symbol'] for x in matches) == ['Egr2', 'Sox10']
    out['tsv'].append({'name': name, 'sha256': digest, 'columns': columns, 'matches': matches})
sample_digest = 'a017d9aacf6337a40b95e6163511732aed21837da2ec43205211fd82ddc1fbb0'
with blob_path(sample_digest).open() as handle:
    out['nae1_sample_map'] = {'sha256': sample_digest, 'rows': list(csv.DictReader(handle, delimiter='\t'))}
archive_digest = '61f3e98f581209f8385a6c4cdee8d1ea1c39b00da761911d8fdf89bb22da7ff1'
with zipfile.ZipFile(blob_path(archive_digest)) as archive:
    for name in ['elife-29241-fig3-data1.xlsx', 'elife-29241-fig4-data1.xlsx', 'elife-29241-fig4-data2.xlsx']:
        raw = archive.read(name)
        digest = hashlib.sha256(raw).hexdigest()
        if name == 'elife-29241-fig3-data1.xlsx':
            assert digest == '3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6'
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
        sheets = []
        for sheet in book:
            text_headers = []
            matches = []
            for row_index, row in enumerate(sheet.iter_rows(), 1):
                if row_index <= 5:
                    text_headers.append({'row': row_index, 'text_cells': {f'{get_column_letter(i)}{row_index}': c.value for i, c in enumerate(row, 1) if c.data_type != 'f' and isinstance(c.value, str)}})
                genes = [c for c in row if c.value in ('Egr2', 'Sox10') and c.data_type != 'f']
                if genes:
                    for cell in genes:
                        matches.append({'symbol': cell.value, 'cell': cell.coordinate, 'row': cell.row,
                                        'nonempty_columns': [get_column_letter(i) for i, c in enumerate(row, 1) if c.value is not None],
                                        'formula_columns': [get_column_letter(i) for i, c in enumerate(row, 1) if c.data_type == 'f']})
            sheets.append({'sheet': sheet.title, 'declared_rows': sheet.max_row, 'declared_columns': sheet.max_column,
                           'initial_text_rows': text_headers, 'regulator_rows': matches})
        book.close()
        out['workbooks'].append({'archive_sha256': archive_digest, 'member': name, 'member_sha256': digest, 'sheets': sheets})
output = q / 'outputs/upstream-regulator-source-locators.json'
output.write_text(json.dumps(out, indent=2, allow_nan=False) + '\n')
print(json.dumps({'output': str(output), 'status': 'verified_source_locators', 'candidate_effects_computed': False}))
