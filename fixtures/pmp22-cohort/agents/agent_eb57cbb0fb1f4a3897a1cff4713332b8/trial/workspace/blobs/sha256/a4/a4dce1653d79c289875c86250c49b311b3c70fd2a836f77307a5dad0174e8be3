"""Preserve only the primary methods article and supplement for a peer critique."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'inputs/kcnq1-methods'
DEST.mkdir(exist_ok=True)
SOURCES = {
    'JCI201297.html': 'https://insight.jci.org/articles/view/201297',
    'JCI201297-supplement.pdf': 'https://insight.jci.org/articles/view/201297/sd/pdf/render/1',
}
for name, url in SOURCES.items():
    body_path = DEST / name
    receipt_path = DEST / (name + '.receipt.json')
    assert not body_path.exists() and not receipt_path.exists(), 'Do not overwrite sources.'
    response = httpx.get(url, follow_redirects=True, timeout=120)
    raw = response.content
    body_path.write_bytes(raw)
    receipt = {
        'url': url, 'final_url': str(response.url), 'status': response.status_code,
        'retrieved_utc': datetime.now(timezone.utc).isoformat(),
        'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
        'content_type': response.headers.get('content-type'),
        'scope': 'Methods/caption critique only; Supporting Data Values not downloaded or analyzed.',
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(receipt))
    response.raise_for_status()
    if name.endswith('.pdf'):
        assert raw.startswith(b'%PDF-')
    for path, classification in [(body_path, 'source'), (receipt_path, 'source-receipt')]:
        result = json.loads(subprocess.run(
            ['./bin/bio', 'object', 'add', str(path), '--classification', classification],
            capture_output=True, text=True, check=True,
        ).stdout)
        assert result['blob'] == hashlib.sha256(path.read_bytes()).hexdigest()
        (DEST / (path.name + '.object.json')).write_text(json.dumps(result, indent=2) + '\n')
        print(path.name, result['blob'])
