import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
data = json.loads((q / 'outputs/nae1-figure-OCR.json').read_text())
for page in data:
    p = page['pdf_page_one_based']
    text = '\n'.join(f"x={line['x']:.3f} y={line['y']:.3f} {line['text']}" for line in page['lines'])
    (q / f'outputs/nae1-ocr-page-{p}.txt').write_text(text + '\n')
    print(p, len(page['lines']), next((line['text'] for line in page['lines'] if line['text'].startswith('Fig.')), ''))
