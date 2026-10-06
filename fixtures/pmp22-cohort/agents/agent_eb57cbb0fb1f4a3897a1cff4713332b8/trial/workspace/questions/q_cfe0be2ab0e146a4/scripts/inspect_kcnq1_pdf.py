"""Inspect local PDF parser availability; save exact relevant page text if available."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'inputs/kcnq1-methods/JCI201297-supplement.pdf'
for module in ['pypdf', 'fitz', 'pdfplumber']:
    print(module, importlib.util.find_spec(module) is not None)
if importlib.util.find_spec('pypdf') is not None:
    from pypdf import PdfReader
    pages = [(i + 1, page.extract_text()) for i, page in enumerate(PdfReader(PDF).pages)]
elif importlib.util.find_spec('fitz') is not None:
    import fitz
    with fitz.open(PDF) as document:
        pages = [(i + 1, page.get_text()) for i, page in enumerate(document)]
elif importlib.util.find_spec('pdfplumber') is not None:
    import pdfplumber
    with pdfplumber.open(PDF) as document:
        pages = [(i + 1, page.extract_text()) for i, page in enumerate(document.pages)]
else:
    raise SystemExit('No local PDF parser available; do not claim graph-label inspection.')
selected = [(number, text) for number, text in pages if text and (
    'Supplemental Figure 4:' in text or 'Any background-subtracted' in text or 'High content imaging:' in text
)]
result = '\n\n'.join(f'PDF page {number}\n{text}' for number, text in selected)
output = ROOT / 'inputs/kcnq1-methods/relevant-pages.txt'
assert not output.exists()
output.write_text(result)
print(result)
