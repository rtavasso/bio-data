"""Preserve selected native sources and locators; no biological analysis or inherited-code execution."""
import csv
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
import zipfile

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OLD = W / 'questions/q_277f20df4b6b47cc'
OUT = Q / 'outputs'
NATIVE = 'GSE139321_Schwann_Cell_Tn5Prime_GEO_Processed.txt'
NATIVE_HASH = 'fe9f2e05e9315040f4237b130b0e53d4bdc68b2ca9b4fc52a22e4f5520e5f7d5'
GZIP_HASH = 'db25ebe101852035d5375434e71c7297c54289ca85a76cefee1b45f8a8bc6144'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def enc(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def blob(h):
    data = (W / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    return data


files = []
members = {}


def add(name, data, origin, **extra):
    assert name not in members
    members[name] = data
    item = dict(member=name, sha256=sha(data), bytes=len(data), origin=origin, **extra)
    files.append(item)
    return item


transport_path = OLD / 'inputs/continuation/transport.json'
transport = json.loads(transport_path.read_text())
receipts = []
header_allow = {'date', 'content-type', 'content-length', 'content-disposition', 'transfer-encoding'}
for pmc in ('PMC3298281', 'PMC7322568', 'PMC5181599'):
    relative = 'inputs/continuation/' + pmc + '.html'
    data = (OLD / relative).read_bytes()
    text = data.decode()
    title_match = re.search(r'<title>(.*?)</title>', text, re.S)
    assert title_match is not None
    title = html.unescape(title_match.group(1)).strip()
    headings = [html.unescape(re.sub('<[^>]*>', '', t)).strip()
                for t in re.findall(r'<h2[^>]*>(.*?)</h2>', text, re.S)]
    assert {'results', 'discussion', 'materials and methods'}.issubset({v.lower() for v in headings})
    record = add('sources/' + pmc + '.html', data, str(Path('questions') / OLD.name / relative),
                 article_id=pmc, title=title, source_representation='exact saved full-text HTML',
                 substantive_sections_present=True)
    selected = []
    for index, entry in enumerate(transport['entries']):
        if entry.get('path') != relative:
            continue
        clean = {k: v for k, v in entry.items() if k != 'headers'}
        if 'headers' in entry:
            clean['headers'] = {k: v for k, v in entry['headers'].items() if k.lower() in header_allow}
            clean['omitted_header_names'] = [k for k in entry['headers'] if k.lower() not in header_allow]
        historical_hash_match = None
        if 'sha256' in entry:
            historical_hash_match = entry['sha256'] == sha(data)
            assert historical_hash_match and entry['bytes'] == len(data)
        elif entry.get('accounting_note'):
            assert entry['bytes'] == len(data)
        selected.append({'json_pointer': '/entries/' + str(index), 'entry': clean,
                         'recorded_hash_matches_saved_bytes': historical_hash_match})
    assert selected
    record['transport_evidence'] = ('inherited complete HTTP receipt with matching saved hash' if
                                   any(v['recorded_hash_matches_saved_bytes'] for v in selected) else
                                   'historical reconciled/incomplete ledger entry only; current hash is not a historical HTTP receipt')
    receipts.append({'article_id': pmc, 'selected_ledger_entries': selected})
receipt_excerpt = {'scope': 'Inherited receipt excerpts, not new requests. Cookie/session headers omitted explicitly.',
                   'parent': str(Path('questions') / OLD.name / 'inputs/continuation/transport.json'),
                   'parent_sha256': sha(transport_path.read_bytes()), 'entries': receipts}
(OUT / 'source-receipts.redacted.json').write_bytes(enc(receipt_excerpt))
add('provenance/source-receipts.redacted.json', enc(receipt_excerpt), 'selected inherited transport entries')

native = blob(NATIVE_HASH)
compressed = blob(GZIP_HASH)
assert gzip.decompress(compressed) == native
add('sources/' + NATIVE, native, 'asset_f7b45493c97bcbf69f884f50fb111ee5',
    source_representation='native tab-delimited text, all source rows and tokens unchanged')
add('sources/' + NATIVE + '.gz', compressed, 'asset_bfb7964142cde09a93a524f3b7ecb0b0',
    source_representation='exact existing compressed parent; decompression equals native text')
(OUT / NATIVE).write_bytes(native)

# Structural source locators only. No normalization, new statistics, or biological effect estimates.
lines = native.splitlines(keepends=True)
rows = list(csv.DictReader(io.StringIO(native.decode()), delimiter='\t'))
header = next(csv.reader([lines[0].decode()], delimiter='\t'))
rpm_columns = [s for s in header if s.endswith(' RPM')]
focal = []
for line_number, row in enumerate(rows, 2):
    if row['TSS id'] in ('5439', '5446'):
        focal.append({'tss_id': row['TSS id'], 'gene_symbol': row['Gene Symbol'],
                      'native_text_line_1based_including_header': line_number,
                      'original_line_sha256': sha(lines[line_number - 1]),
                      'chromosome_token': row['TSS Chr'], 'start_token': row['TSS Start'],
                      'end_token': row['TSS End'], 'strand_token': row['TSS Strand']})
assert [v['native_text_line_1based_including_header'] for v in focal] == [817, 824]
assert len(rpm_columns) == 14 and len(rows) == 4993
# Verify the inherited source-row labels without comparing/recomputing effect values.
original_panel = OLD / 'outputs/tss-regulatory-panel.tsv'
old_rows = list(csv.DictReader(io.StringIO(original_panel.read_text()), delimiter='\t'))
for item in focal:
    match = next(v for v in old_rows if v['TSS id'] == item['tss_id'])
    assert match['source_row'] == str(item['native_text_line_1based_including_header'])

profile = json.loads((Q / 'inputs/tss-native-profile.json').read_text())
source_manifests = [v['facts']['source_manifest'] for v in profile['profiles'] if 'source_manifest' in v['facts']]
contexts = profile['profiles'][0]['facts'].get('related_source_context', [])
metadata = []
for context in contexts:
    fields = context.get('body', {}).get('fields', {})
    kept = {k: v for k, v in fields.items() if k in (
        'Sample_geo_accession', 'Sample_title', 'Sample_source_name_ch1', 'Sample_organism_ch1',
        'Sample_characteristics_ch1', 'Sample_description', 'Sample_data_processing', 'Sample_supplementary_file')}
    if kept and kept not in metadata:
        metadata.append(kept)
ancestry = json.loads((Q / 'inputs/tss-archive-profile.json').read_text())
source_context = {'scope': 'Selected fields from current local catalog readback of inherited source metadata',
                  'native_asset': 'asset_f7b45493c97bcbf69f884f50fb111ee5',
                  'source_manifests': source_manifests, 'source_context': metadata,
                  'archive_relationships': ancestry.get('relationships', []),
                  'gzip_note': 'Newer inventory asset_98dc5750985533498ba0638b486fea15 is listed-only; older archive asset_bfb7964142cde09a93a524f3b7ecb0b0 has the verified local parent bytes.',
                  'readback_sha256': sha((Q / 'inputs/tss-native-profile.json').read_bytes())}
add('provenance/tss-source-context.json', enc(source_context), 'local catalog readback; not a newly acquired HTTP response')

manifest = {'version': 1, 'question': Q.name,
            'request_post': 'post_fd76a69fce5f44ae8900b2e3083c6c4c',
            'source_question': OLD.name, 'purpose': 'Selective unchanged scientific-source access; no scientific rerun',
            'files': files,
            'tss_structure': {'data_rows': len(rows), 'source_columns': header,
                              'rpm_column_count': len(rpm_columns), 'rpm_columns': rpm_columns,
                              'Pmp22_labelled_rows': sum(v['Gene Symbol'] == 'Pmp22' for v in rows),
                              'focal_locators': focal, 'header_lines': 1,
                              'source_units': 'Source-labelled RPM, not raw counts; source contrast/FDR columns unchanged.',
                              'assembly': 'rn5 as explicitly recorded in preserved source metadata',
                              'coordinate_policy': 'Start/end/strand tokens preserved; no BED conversion, transcript assignment or human liftOver.',
                              'sample_policy': 'Individual library-labelled columns, not a new donor-independence claim.',
                              'worksheet_policy': 'Peer worksheet lines 818/825 are attributed to that separate representation, not assumed equal to native text lines 817/824.'},
            'native_parent_identity': {'compressed_sha256': GZIP_HASH, 'uncompressed_sha256': NATIVE_HASH,
                                       'decompression_byte_identity': True},
            'historical_panel_locator': {'artifact': 'artifact_6d29032908e5607507672edc51c6d6fa6a282a4e0bd0e2e37924be0bfde43fea',
                                         'path': 'questions/' + OLD.name + '/outputs/tss-regulatory-panel.tsv',
                                         'sha256': sha(original_panel.read_bytes()),
                                         'source_row_definition': '1-based physical native-text line, includes one header'},
            'PMC6077802': {'included': False, 'status': 'No inherited complete article file located',
                          'searched': ['original question filenames', 'local data/artifact text indexes', 'workspace blob PMC/DOI matches'],
                          'matches_disposition': 'Other papers cite it; fetched peer derivations contain metadata, failure receipts, curation and thesis text, not an inherited exact full-article file.',
                          'not_substituted': 'No thesis/abstract/citation substituted for the requested exact article.'},
            'community_context': {'publication': 'post_3f7bd6e66753476fb33ec6d9da9cbcc8',
                                  'mapping_artifact': 'artifact_46c490850c14f6afe9d32cb74b32ad94e60d828de0751236d25c51fcc079771a',
                                  'use': 'Peer completed audit and primer-backed associations inspected; no replication claimed.'},
            'execution_scope': 'Reading source bytes/headers/locators, checksums and gzip identity, selective packaging only; no downloaded/inherited code or scientific reanalysis.',
            'new_scientific_source_http_requests': 0}
manifest_data = enc(manifest)
(OUT / 'source-locator-manifest.json').write_bytes(manifest_data)
members['source-locator-manifest.json'] = manifest_data
archive_path = OUT / 'cis-source-evidence.zip'
with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(members.items()):
        archive.writestr(name, data)
with zipfile.ZipFile(archive_path) as archive:
    assert set(archive.namelist()) == set(members)
    for name, data in members.items():
        assert archive.read(name) == data
verification = {'valid': True, 'scope': 'source byte preservation and locator checks only',
                'archive_members': len(members), 'archive_bytes': archive_path.stat().st_size,
                'archive_sha256': sha(archive_path.read_bytes()), 'manifest_sha256': sha(manifest_data),
                'native_text_bytes': len(native), 'compressed_parent_bytes': len(compressed),
                'native_text_sha256': NATIVE_HASH, 'compressed_parent_sha256': GZIP_HASH,
                'gzip_identity': True, 'tss_data_rows': len(rows), 'rpm_columns': len(rpm_columns),
                'pmp22_rows': manifest['tss_structure']['Pmp22_labelled_rows'], 'focal_locators': focal,
                'scientific_rerun': False}
(OUT / 'byte-verification.json').write_bytes(enc(verification))
print(json.dumps(verification, indent=2))
