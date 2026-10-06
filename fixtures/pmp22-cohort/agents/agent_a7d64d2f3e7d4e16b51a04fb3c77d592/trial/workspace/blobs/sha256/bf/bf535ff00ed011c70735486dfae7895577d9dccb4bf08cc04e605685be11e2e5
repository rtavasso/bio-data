"""Verify supplied bytes and render static article text; no biological recalculation."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import textwrap
import zipfile

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs/handoff-r001'
DEST = Q / 'inputs/handoff-r001'
DEST.mkdir(exist_ok=True)
meta = json.loads((OUT / 'bundle-artifact.json').read_text())
locmeta = json.loads((OUT / 'locator-artifact.json').read_text())
bundle = Path(meta['path'])
locator_bytes = Path(locmeta['path']).read_bytes()
locator = json.loads(locator_bytes)
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == meta['output_blob']
assert hashlib.sha256(locator_bytes).hexdigest() == locmeta['output_blob']
checks = []
with zipfile.ZipFile(bundle) as z:
    assert z.testzip() is None
    assert set(z.namelist()) == {x['member'] for x in locator['files']} | {'source-locator-manifest.json'}
    assert z.read('source-locator-manifest.json') == locator_bytes
    for item in locator['files']:
        name = item['member']
        p = PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts
        b = z.read(name)
        assert len(b) == item['bytes']
        assert hashlib.sha256(b).hexdigest() == item['sha256']
        copied = p.suffix in ('.json', '.html', '.tsv', '.txt')
        if copied:
            target = DEST / p
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert target.read_bytes() == b
            else:
                target.write_bytes(b)
        checks.append({'member': name, 'sha256': item['sha256'], 'bytes': len(b), 'copied_static': copied})
    member_count = len(z.namelist())


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'figcaption') and not self.skip:
            at = dict(attrs)
            self.parts.append('\n\n' + (f'[{at["id"]}] ' if 'id' in at else ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'figcaption') and not self.skip:
            self.parts.append('\n\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


parser = TextOnly()
parser.feed((DEST / 'sources/PMC6607759.html').read_text())
paragraphs = [' '.join(x.split()) for x in ''.join(parser.parts).split('\n\n') if x.strip()]
text = '\n\n'.join(textwrap.fill(p, 115) for p in paragraphs)
assert 'PMP22 Regulates Cholesterol Trafficking' in text
assert 'Materials and Methods' in text and 'Discussion' in text
(OUT / 'PMC6607759-readable.txt').write_text(text)
summary = {'scope': 'local verification/extraction of inherited source handoff, not biological reanalysis',
           'bundle_sha256': meta['output_blob'], 'locator_sha256': locmeta['output_blob'],
           'zip_members': member_count, 'named_members_verified': len(checks), 'embedded_locator_matches': True,
           'members': checks, 'new_HTTP_requests': 0, 'imported_code_executed': False,
           'large_archives_or_docx_fetched': False, 'prior_numerical_outputs_recomputed': False}
(OUT / 'handoff-verification.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
print(json.dumps({k: v for k, v in summary.items() if k != 'members'}))
