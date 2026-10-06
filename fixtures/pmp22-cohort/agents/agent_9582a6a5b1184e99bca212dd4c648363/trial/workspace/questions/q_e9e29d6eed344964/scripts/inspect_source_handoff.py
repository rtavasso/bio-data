"""Inspect a peer's static source handoff; never execute imported code."""
import csv
import hashlib
import io
import json
import zipfile
from html.parser import HTMLParser
from pathlib import Path

q = Path(__file__).resolve().parents[1]
s = q / 'sources'

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1
        elif tag in ('p', 'h1', 'h2', 'h3', 'h4', 'tr', 'section', 'figcaption', 'div') and not self.skip:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

manifest = None
for kind in ('manifest', 'bundle'):
    meta = json.loads((s / f'source-handoff-{kind}-artifact.json').read_text())
    payload = Path(meta['path'])
    assert hashlib.sha256(payload.read_bytes()).hexdigest() == meta['output_blob']
    print('VERIFIED_ARTIFACT', kind, meta['id'], meta['output_blob'])
    if kind == 'manifest':
        manifest = json.loads(payload.read_text())
        (s / 'source-handoff-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print('MANIFEST', json.dumps(manifest, indent=2))
    else:
        assert manifest is not None
        with zipfile.ZipFile(payload) as archive:
            assert archive.testzip() is None
            print('ARCHIVE_MEMBERS', json.dumps(archive.namelist(), indent=2))
            (s / 'source-handoff-members.json').write_text(json.dumps(archive.namelist(), indent=2) + '\n')
            destination = s / 'handoff'
            destination.mkdir(exist_ok=True)
            for item in manifest['files']:
                data = archive.read(item['member'])
                assert len(data) == item['bytes']
                assert hashlib.sha256(data).hexdigest() == item['sha256']
                name = Path(item['member']).name
                (destination / name).write_bytes(data)
                if name.endswith('.html'):
                    parser = PlainText()
                    parser.feed(data.decode('utf-8'))
                    lines = [' '.join(line.split()) for line in ''.join(parser.parts).splitlines()]
                    (destination / name.replace('.html', '.txt')).write_text('\n'.join(line for line in lines if line) + '\n')
            native = (destination / 'GSE139321_Schwann_Cell_Tn5Prime_GEO_Processed.txt').read_text()
            table = list(csv.DictReader(io.StringIO(native), delimiter='\t'))
            rpm = [key for key in table[0] if key.endswith(' RPM')]
            pmp22 = [row for row in table if row['Gene Symbol'] == 'Pmp22']
            assert len(table) == manifest['tss_structure']['data_rows']
            assert len(rpm) == manifest['tss_structure']['rpm_column_count']
            assert len(pmp22) == manifest['tss_structure']['Pmp22_labelled_rows']
            for focal in manifest['tss_structure']['focal_locators']:
                line = focal['native_text_line_1based_including_header']
                assert table[line - 2]['TSS id'] == focal['tss_id']
            print('VERIFIED_SOURCE_STRUCTURE', len(table), 'ROWS', len(rpm), 'RPM_COLUMNS', len(pmp22), 'PMP22_ROWS')
post = json.loads((s / 'community/source-handoff-publication.json').read_text())
(s / 'community/source-handoff-publication.md').write_text(post['content']['body'])
