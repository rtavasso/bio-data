"""Inspect selected native schema, sequence annotations and possible export duplication."""
import csv
import io
import json
from pathlib import Path
import zipfile
import openpyxl
q = Path(__file__).resolve().parents[1]
# Only safe text/XLSX reading. No embedded code is executed.
a = zipfile.ZipFile(q/'inputs/http/pum-tcam-supp-r001.payload')
b = zipfile.ZipFile(io.BytesIO(a.read('cells-09-00984-s001.zip')))
b = zipfile.ZipFile(io.BytesIO(b.read('FINAL Supplementary Files.zip')))
result = {'tcam_members': [{'name': x.filename, 'bytes': x.file_size} for x in b.infolist()], 'tcam_tables': []}
for n in b.namelist():
    if not n.endswith('.xlsx'):
        continue
    wb = openpyxl.load_workbook(io.BytesIO(b.read(n)), read_only=True, data_only=False)
    for s in wb:
        s.reset_dimensions()
        first, hits, count = [], [], 0
        for r in s.iter_rows(values_only=True):
            if not any(x is not None for x in r):
                continue
            count += 1
            if len(first) < 4:
                first.append(r[:25])
            if any(str(v).upper() in ['PMP22','PUM1','PUM2','NM_000304','NM_153321'] for v in r):
                hits.append(r)
        result['tcam_tables'].append({'member': n, 'sheet': s.title, 'nonempty_rows': count, 'first': first, 'targets': hits})
    wb.close()
a = zipfile.ZipFile(q/'inputs/http/pum-bruchase-supp-r001.payload')
n = 'supp_077362.120_Supplemental_Bru_seq_and_BruChase_seq_model_coefficients.tsv'
rows = list(csv.DictReader(io.StringIO(a.read(n).decode()), delimiter='\t'))
fields = ['log2FoldChange','lfcSE','stat','pvalue','padj']
result['bruchase_export_audit'] = {'rows': len(rows), 'unique_genes': len({r['Gene'] for r in rows}), 'time_and_interaction_equal': {f: sum(r['sixhr_vs_zerohr_time_term_'+f]==r['conditiontime_interaction_term_'+f] for r in rows) for f in fields}, 'interaction_padj_not_NA': sum(r['conditiontime_interaction_term_padj']!='NA' for r in rows)}
nested = zipfile.ZipFile(io.BytesIO(a.read('supp_077362.120_Supplemental_features_for_machine_learning.zip')))
result['feature_members'] = [{'name': x.filename, 'bytes': x.file_size} for x in nested.infolist()]
for name in nested.namelist():
    if name.endswith(('.tsv','.txt','.csv')):
        text = nested.read(name).decode()
        lines = text.splitlines()
        result.setdefault('feature_text_probes', []).append({'member': name, 'line_count': len(lines), 'first': lines[0][:2500], 'pmp22': [line[:10000] for line in lines if line.startswith('PMP22\t') or line.startswith('PMP22,')]})
(q/'outputs/native-schema-followup-r001.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print(json.dumps(result, allow_nan=False))
