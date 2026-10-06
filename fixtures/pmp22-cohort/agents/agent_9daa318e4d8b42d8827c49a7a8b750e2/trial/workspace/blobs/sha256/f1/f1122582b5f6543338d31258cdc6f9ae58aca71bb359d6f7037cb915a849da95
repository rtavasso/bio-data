"""Export selected unchanged lipid evidence; no summary arithmetic or biological reanalysis."""
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import zipfile

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OLD = W / 'questions/q_277f20df4b6b47cc'
OUT = Q / 'outputs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def enc(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def blob(h):
    data = (W / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    return data


inspection = json.loads((OUT / 'archive-inspection.json').read_text())
assert inspection['valid']
if sys.argv[1:] == ['supplement']:
    data = (OLD / 'inputs/upstream/ADVS-13-e20323-s002.docx').read_bytes()
    assert sha(data) == inspection['docx_sha256'] and len(data) == inspection['docx_bytes']
    (OUT / 'ADVS-13-e20323-s002.docx').write_bytes(data)
    print(json.dumps({'operation': 'unchanged native DOCX copy', 'sha256': sha(data), 'bytes': len(data)}))
    raise SystemExit(0)
assert not sys.argv[1:]
MEMBERS = {}
FILES = []


def add(name, data, origin, **extra):
    assert name not in MEMBERS
    MEMBERS[name] = data
    item = dict(member=name, sha256=sha(data), bytes=len(data), origin=origin, **extra)
    FILES.append(item)
    return item


source_path = OLD / 'inputs/continuation/PMC6607759.html'
source = source_path.read_bytes()
headings = [html.unescape(re.sub('<[^>]*>', '', x)).strip()
            for x in re.findall(r'<h[12][^>]*>(.*?)</h[12]>', source.decode(), re.S)]
assert {'Materials and Methods', 'Results', 'Discussion'}.issubset(set(headings))
assert 'PMP22 Regulates Cholesterol Trafficking and ABCA1-Mediated Cholesterol Efflux' in headings
add('sources/PMC6607759.html', source, 'questions/' + OLD.name + '/inputs/continuation/PMC6607759.html',
    representation='complete inherited primary HTML, not a challenge page')
originals = []
for name in ['original-lipid-artifact.json', 'original-lipid-table-artifact.json']:
    path = Q / 'inputs' / name
    d = json.loads(path.read_text())
    m = d['manifest']
    output = blob(m['output']['blob'])
    assert output == (OLD / 'outputs' / m['output']['name']).read_bytes()
    add('original-results/' + m['output']['name'], output, d['id'])
    add('provenance/' + d['id'] + '.json', path.read_bytes(), 'current catalog readback of original unchanged derivation')
    for inp in m['derivation']['inputs']:
        assert blob(inp['blob']) == source
    for h in m['derivation']['code']:
        original_code = blob(h)
        assert original_code == (OLD / 'scripts/analyze_lipid_summary.py').read_bytes()
        if 'original-code/analyze_lipid_summary.py' not in MEMBERS:
            add('original-code/analyze_lipid_summary.py', original_code, d['id'], execution='not executed')
    originals.append(dict(artifact=d['id'], output=m['output'], original_command=m['derivation']['command']))
for rel in ['outputs/upstream/FDFT1-data-inventory.json', 'outputs/upstream/FDFT1-archive-inventory.json',
            'scripts/upstream_inventory.py']:
    add('inherited/' + rel, (OLD / rel).read_bytes(), 'questions/' + OLD.name + '/' + rel,
        scope='exact historical bytes; not a new execution of the inherited producer')
registration_path = OLD / 'outputs/continuation-registration.json'
registration = json.loads(registration_path.read_text())
selected = {n: registration['outputs'][n] for n in ['lipid-summary-analysis.json', 'lipid-protein-summary-derived.tsv']}
add('provenance/original-registration-excerpts.json', enc(dict(parent='questions/' + OLD.name + '/outputs/continuation-registration.json',
    parent_sha256=sha(registration_path.read_bytes()), pointer='/outputs', selected=selected)), 'selected original registration receipts')
for name in ['archive-inspection.json', 'inspection-execution-r001.json', 'pmc6623163-candidate-inspection.json', 'candidate-article-identities.txt']:
    add('verification/' + name, (OUT / name).read_bytes(), 'current local byte/representation inspection')
add('verification/inspect_archives.py', (Q / 'scripts/inspect_archives.py').read_bytes(), 'current archive inspection code')

allowed = {'url', 'final_url', 'path', 'name', 'status', 'http_status', 'bytes', 'sha256',
           'started', 'finished', 'content_type', 'error', 'accounting_note'}
receipts = []
transport_path = OLD / 'inputs/continuation/transport.json'
transport = json.loads(transport_path.read_text())
for i, entry in enumerate(transport['entries']):
    if entry.get('path') == 'inputs/continuation/PMC6607759.html':
        assert entry['sha256'] == sha(source) and entry['bytes'] == len(source)
        receipts.append(dict(parent='questions/' + OLD.name + '/inputs/continuation/transport.json',
                             parent_sha256=sha(transport_path.read_bytes()), pointer='/entries/' + str(i),
                             entry={k: v for k, v in entry.items() if k in allowed}, matching_saved_bytes=True))
assert receipts
failure_files = []
for name, disposition in [('PMC6623163.xml', 'HTTP500 JSON error, not article XML'),
                          ('PMC6623163.html', 'HTTP200 reCAPTCHA challenge, not primary article'),
                          ('PMC6623163-biocc.json', 'HTTP200 non-JSON BioC no-result response')]:
    raw = (OLD / 'inputs/upstream' / name).read_bytes()
    rp = OLD / 'inputs/upstream/receipts' / (name + '.json')
    receipt = json.loads(rp.read_text())
    assert receipt['sha256'] == sha(raw) and receipt['bytes'] == len(raw)
    failure_files.append(dict(path='questions/' + OLD.name + '/inputs/upstream/' + name,
                              sha256=sha(raw), bytes=len(raw), disposition=disposition, exported_as_primary=False))
    receipts.append(dict(parent='questions/' + OLD.name + '/inputs/upstream/receipts/' + rp.name,
                         parent_sha256=sha(rp.read_bytes()), entry={k: v for k, v in receipt.items() if k in allowed},
                         matching_saved_bytes=True, interpretation=disposition))
rp = OLD / 'inputs/upstream/receipts/FDFT1-supplements.zip.json'
r = json.loads(rp.read_text())
assert r['sha256'] == inspection['outer_sha256'] and r['bytes'] == inspection['outer_bytes']
receipts.append(dict(parent='questions/' + OLD.name + '/inputs/upstream/receipts/' + rp.name,
                     parent_sha256=sha(rp.read_bytes()), entry={k: v for k, v in r.items() if k in allowed},
                     interpretation='inherited archive acquisition, verified locally; not a new HTTP request'))
receipt_export = dict(scope='Selected inherited receipts, not current source acquisition; headers/session material omitted.', entries=receipts)
(OUT / 'source-receipts.redacted.json').write_bytes(enc(receipt_export))
add('provenance/source-receipts.redacted.json', enc(receipt_export), 'selected inherited receipts')
status = dict(PMC6607759='Exact requested saved full text included.',
              PMC6623163=dict(full_text_located=False, saved_responses=failure_files,
                             search_scope='Named local files, local data/artifact catalogs and 24 PMC-ID blob hits inspected; article-like hits are PMC5802790 and a TEAD paper. Peer primary abstract is not substituted for full text.',
                             new_source_requests=0),
              FDFT1=dict(outer_archive_sha256=inspection['outer_sha256'], outer_archive_included=False,
                         nested_archive_sha256=inspection['nested_sha256'], nested_archive_included=False,
                         native_docx=dict(name=inspection['docx_member'], sha256=inspection['docx_sha256'],
                                          bytes=inspection['docx_bytes'], delivery='separate optional artifact; not in this core ZIP'),
                         inventory='Exact original nested/outer inventories preserved and checked against actual archive directory entries.',
                         matrix_limit='Nested ZIP has blot-image PDF, microscopy-image PDF and STR PDF; DOCX has figures/reagents/primers. No sample-level genotype RNA matrix supplied, and no inference of PMP22 absence or zero.'))
manifest = dict(question=Q.name, source_question=OLD.name, request='post_a37ef5629cc842b39412d0876de9172b',
                purpose='Selective immutable evidence access; no scientific rerun or summary-product recalculation',
                files=FILES, original_artifacts=originals, availability=status,
                scientific_limits='Original descriptive group-summary product remains unpaired, without covariance/uncertainty or a formal null test; not absolute surface, functional myelin or transcriptional feedback.',
                provenance_limits='Original lipid command arrays are empty. Native DOCX archive identity was checked in this session, separately from inherited acquisition. Large archives are omitted; hashes/inventories/receipts retained. No fabricated retrospective producer receipt.',
                current_peer_context=dict(post='post_78aab10c0b084ef89511249f43fe0180',
                                          artifact='artifact_eefcd493a7872cd9f1c9da722ef0e88fa5d5464ad2f05c9a5cbe21b5e2350478',
                                          use='Completed endpoint/age/context audit inspected; no reanalysis or independent replication.'))
manifest_bytes = enc(manifest)
(OUT / 'source-locator-manifest.json').write_bytes(manifest_bytes)
MEMBERS['source-locator-manifest.json'] = manifest_bytes
archive_path = OUT / 'lipid-source-evidence.zip'
with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(MEMBERS.items()):
        archive.writestr(name, data)
with zipfile.ZipFile(archive_path) as archive:
    assert set(archive.namelist()) == set(MEMBERS)
    for name, data in MEMBERS.items():
        assert archive.read(name) == data
verification = dict(valid=True, archive_sha256=sha(archive_path.read_bytes()), archive_bytes=archive_path.stat().st_size,
                    archive_members=len(MEMBERS), original_artifacts=len(originals), source_html_sha256=sha(source),
                    source_receipt_matches=True, native_supplement_identity=inspection['docx_sha256'],
                    original_inventories_match=True, PMC6623163_full_text_included=False, scientific_rerun=False)
(OUT / 'byte-verification.json').write_bytes(enc(verification))
print(json.dumps(verification, indent=2))
