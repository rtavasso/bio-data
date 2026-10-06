"""Selective inherited-byte export. No scientific analysis or inherited code execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
ROOT = W.parent
OLD = W / 'questions/q_277f20df4b6b47cc'
OUT = Q / 'outputs'
BIO = ROOT / 'bin/bio'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def blob(value):
    p = W / 'blobs/sha256' / value[:2] / value
    data = p.read_bytes()
    assert digest(data) == value
    return data


members = {}
files = []
checks = []


def add(name, data, origin, role):
    assert name not in members
    members[name] = data
    files.append({'member': name, 'sha256': digest(data), 'bytes': len(data),
                  'origin': origin, 'role': role})


def add_old(relative, role):
    data = (OLD / relative).read_bytes()
    add('inherited/' + relative, data,
        str(Path('questions') / OLD.name / relative), role)
    return data


sources = ['inputs/continuation/PMC8191293.xml',
           'inputs/continuation/PMC4227013.xml',
           'inputs/continuation/PMC8191293-mmc2.xlsx',
           'inputs/continuation/PXD023091-files.json']
source_bytes = {name: add_old(name, 'native inherited scientific source') for name in sources}
reg_path = OLD / 'outputs/continuation-registration.json'
registrations = json.loads(reg_path.read_text())
selected = {k: v for k, v in registrations['outputs'].items() if k.startswith('protein-')}
assert len(selected) == 6
original_input_hashes = set()
original_artifacts = []
for name, receipt in selected.items():
    aid = receipt['artifact']
    result = subprocess.run([str(BIO), 'artifact', 'show', aid],
                            capture_output=True, text=True, check=True)
    shown = json.loads(result.stdout)
    raw_manifest = blob(shown['manifest_blob'])
    manifest = json.loads(raw_manifest)
    data = (OLD / 'outputs' / name).read_bytes()
    assert digest(data) == shown['output_blob'] == receipt['output_blob']
    assert blob(shown['output_blob']) == data
    add('inherited/outputs/' + name, data, aid, 'unchanged existing computational output')
    add('provenance/artifacts/' + aid + '.json', raw_manifest,
        shown['manifest_blob'], 'exact original immutable artifact manifest')
    for item in manifest['derivation']['inputs']:
        original_input_hashes.add(item['blob'])
        blob(item['blob'])
    for code_hash in manifest['derivation']['code']:
        code = blob(code_hash)
        assert code == (OLD / 'scripts/analyze_protein_interactors.py').read_bytes()
    checks.append({'artifact': aid, 'output_sha256': digest(data),
                   'manifest_sha256': shown['manifest_blob'], 'input_code_output_verified': True})
    original_artifacts.append(aid)
assert original_input_hashes == {digest(source_bytes[name]) for name in sources
                                if not name.endswith('PMC4227013.xml')}
add_old('scripts/analyze_protein_interactors.py', 'historical producer; preserved but not executed')
add_old('outputs/protein-analysis-log.txt', 'historical stdout; not a new execution receipt')
add_old('outputs/protein-analysis-stderr.txt', 'historical stderr; not a new execution receipt')
add('provenance/selected-original-registration-receipts.json', encode({
    'parent': str(Path('questions') / OLD.name / 'outputs/continuation-registration.json'),
    'parent_sha256': digest(reg_path.read_bytes()), 'selected_outputs': selected}),
    'selected unchanged entries from original registration ledger', 'inherited registration excerpt')

transport_path = OLD / 'inputs/continuation/transport.json'
transport = json.loads(transport_path.read_text())
zip_relative = 'inputs/continuation/PMC8191293-supplementary.zip'
needed = {sources[0], sources[1], sources[3], zip_relative}
entries = []
allowed_headers = {'date', 'content-type', 'content-length', 'content-disposition', 'transfer-encoding'}
for index, entry in enumerate(transport['entries']):
    if entry.get('path') not in needed:
        continue
    data = (OLD / entry['path']).read_bytes()
    assert entry['completed'] and entry['status'] == 200
    assert len(data) == entry['bytes'] and digest(data) == entry['sha256']
    clean = {k: v for k, v in entry.items() if k != 'headers'}
    clean['headers'] = {k: v for k, v in entry.get('headers', {}).items()
                        if k.lower() in allowed_headers}
    entries.append({'original_json_pointer': '/entries/' + str(index),
                    'receipt': clean, 'local_byte_identity_verified': True,
                    'omitted_header_names': [k for k in entry.get('headers', {})
                                             if k.lower() not in allowed_headers]})
assert len(entries) == len(needed) and {x['receipt']['path'] for x in entries} == needed
with zipfile.ZipFile(OLD / zip_relative) as archive:
    matched = [i for i in archive.infolist() if i.filename.endswith('mmc2.xlsx')]
    assert len(matched) == 1
    item = matched[0]
    workbook_bytes = archive.read(item)
    assert workbook_bytes == source_bytes['inputs/continuation/PMC8191293-mmc2.xlsx']
    workbook_origin = {'archive': str(Path('questions') / OLD.name / zip_relative),
                       'archive_sha256': digest((OLD / zip_relative).read_bytes()),
                       'member': item.filename, 'member_crc32': item.CRC,
                       'member_sha256': digest(workbook_bytes), 'bytes': len(workbook_bytes),
                       'exact_match': True, 'checked_now_not_historical_extraction_receipt': True}
source_receipts = {
    'scope': 'Selected inherited HTTP receipts; not requests executed in this session.',
    'parent': str(Path('questions') / OLD.name / 'inputs/continuation/transport.json'),
    'parent_sha256': digest(transport_path.read_bytes()),
    'redaction': 'Header allowlist only; cookies/session headers and unrelated requests omitted. Original ledger unchanged locally.',
    'entries': entries, 'native_workbook_origin': workbook_origin,
    'workbook_request': 'No separate workbook HTTP request is claimed; byte identity to ZIP member verified.'}
(OUT / 'source-receipts.redacted.json').write_bytes(encode(source_receipts))
add('provenance/source-receipts.redacted.json', encode(source_receipts),
    'selected inherited transport entries with explicit redaction', 'source receipts and member identity')

summary = json.loads((OLD / 'outputs/protein-analysis-summary.json').read_text())
manifest = {
    'version': 1, 'question': Q.name, 'source_question': OLD.name,
    'request_post': 'post_311acb7126bf4b229f8ede00ae92f18e',
    'purpose': 'Selective evidence access, not new scientific results or independent replication.',
    'original_artifacts': original_artifacts,
    'files': files,
    'inherited_counts_not_recomputed': {'counts': summary['counts'], 'selected_entries': sum(summary['counts'].values()),
                                      'union': summary['union'], 'all_three': summary['all_three']},
    'scientific_limits': [summary[k] for k in ('endpoint', 'material', 'selection', 'fresh_tests', 'batch_warning')],
    'historical_execution_limit': 'Existing manifests retain code/input/output/environment but command=[]; stdout/stderr are preserved. No historical producer-specific exit receipt was reconstructed.',
    'historical_budget_limit': 'The original summary PXD023091 per-file cap is historical, not a current collection restriction.',
    'unchanged_blockers': 'PXD043917 LFQ and P7/P15 matching are outside this handoff and unresolved.',
    'peer_context': {'publication': 'post_ede3429c8d7a4485b7681fbf94798066',
                     'inspected_artifact': 'artifact_87fa9f1eca8180a7f98c6bf0f2b2a69596b82c835cd54ab988586c76eba6d0a1',
                     'disposition': 'Peer already audited these sources; preserve its UGGT1 abstract/results discrepancy and endpoint distinctions, without claiming our own reanalysis.'},
    'excluded': ['full workspace', 'unrelated sources', 'supplementary ZIP except exact mmc2 workbook',
                 'raw spectra', 'unfiltered transport ledger/cookie headers', 'downloaded executable code'],
    'session_source_http_requests': 0,
}
manifest_data = encode(manifest)
(OUT / 'share-manifest.json').write_bytes(manifest_data)
members['share-manifest.json'] = manifest_data
package = OUT / 'protein-evidence.zip'
with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(members.items()):
        archive.writestr(name, data)
with zipfile.ZipFile(package) as archive:
    assert set(archive.namelist()) == set(members)
    for name, data in members.items():
        assert archive.read(name) == data
verification = {'valid': True, 'scope': 'byte preservation and selective packaging only',
                'original_artifacts': checks, 'receipt_payloads_verified': len(entries),
                'workbook_member_identity': workbook_origin,
                'archive_members_verified': len(members), 'package_bytes': package.stat().st_size,
                'package_sha256': digest(package.read_bytes()),
                'manifest_sha256': digest(manifest_data), 'scientific_rerun': False}
(OUT / 'byte-verification.json').write_bytes(encode(verification))
print(json.dumps(verification, indent=2))
