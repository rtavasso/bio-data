"""Verify selected archive lineage and classify already-discovered local article candidates."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
old = w / 'questions/q_277f20df4b6b47cc'
out = q / 'outputs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


parent_path = old / 'inputs/upstream/FDFT1-supplements.zip'
parent_data = parent_path.read_bytes()
docx_path = old / 'inputs/upstream/ADVS-13-e20323-s002.docx'
nested_path = old / 'inputs/upstream/ADVS-13-e20323-s001.zip'
with zipfile.ZipFile(io.BytesIO(parent_data)) as parent:
    outer = [dict(name=x.filename, size=x.file_size, compressed=x.compress_size) for x in parent.infolist()]
    assert outer == json.loads((old / 'outputs/upstream/FDFT1-archive-inventory.json').read_text())
    docx = parent.read(docx_path.name)
    nested = parent.read(nested_path.name)
    assert docx == docx_path.read_bytes() and nested == nested_path.read_bytes()
with zipfile.ZipFile(io.BytesIO(nested)) as archive:
    members = [dict(name=x.filename, size=x.file_size, compressed=x.compress_size) for x in archive.infolist()]
assert members == json.loads((old / 'outputs/upstream/FDFT1-data-inventory.json').read_text())
receipt = json.loads((old / 'inputs/upstream/receipts/FDFT1-supplements.zip.json').read_text())
assert receipt['sha256'] == sha(parent_data) and receipt['bytes'] == len(parent_data)
result = dict(valid=True, scope='Exact byte and archive-directory comparison only; no raw images processed',
              outer_sha256=sha(parent_data), outer_bytes=len(parent_data), outer_inventory_matches=True,
              docx_sha256=sha(docx), docx_bytes=len(docx), docx_member=docx_path.name,
              docx_matches_local_extracted_copy=True, nested_sha256=sha(nested), nested_bytes=len(nested),
              nested_member=nested_path.name, nested_inventory_matches=True, nested_inventory=members,
              source_receipt_matches=True, excluded_payloads='Outer ZIP and nested raw-image ZIP intentionally not exported; locators, exact inventories and hashes retained.')
(out / 'archive-inspection.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print('ARCHIVE', json.dumps(result, indent=2))
# These content-hash candidates came from the explicit search_files result, not a new scan.
hashes = '''be19943af1e5e2f67379b719ae36c91c6d0a50e5de4e59db9f46703e44b23e89
d8358ab1d18c42d1e9a48c6205b0a6c0da8a2bb2a873add6903d01f0d4b1ae80
0c06e7949119f566be63d33f36a2fa17a0b07469c619c6634d741ff99158bc3f
d6e5c0718b0497db3ee434ca389047945e908ffb635824409d8e736eabf45730
37669e33963e54daaade7891715c5b4d2b5cd2480b03289cb9eb8ca3e4054c3a
135aea310b27d638fe62e9c5b9d9e72bea9aa5c94d45f18bee625f828536531e
a203ea520f6a2a64f5435f9304f7e968de4b4e463c8720d6818d6399b9514b08
61ba6721c747263e3df91a3bee14a134b00951f403d9440959bbe483d7814c57
ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3
cd2af74b87e605be4055d48ee00ab809a8a639fbefe84e4f10bb8555e000ab49
f2f21e5814c76ead6de4699e955581ba37cf748e4fb6b332be22e00ac18a845c
35047aa3b044377968c607692f73ca42622dd77942285a0145b095602ef58ff2
fd1f0398baf623eb71438049fb25eddcc6b959583ace7912cc3a60b9157a8fd3
f35b2baafa70cc911b83cabf71ff11aa80b9671ec7312e89f25a3695e4b74c0c
3297901ed5c7890064221f617b6b624dab33ec47651de1f86d86ecabd0e1ef92
dc02db5a4985a43f778fb4f83e1a934bd45737fa78aa73a6eae425bddf291287
8ae15b8966ca7f158600adeed4038ad9bed93480ba742255f2d78a3fa6fb15b0
7b0a5fe4f9c5cdee5f5c45046457dc74a9716945bb88f7aff0f982ce844280ac
82c984a98ae9f1c0a01b685f5dd87e2b258fa81e3c087728f0b5e2350dba1513
65421a34f6181092f291894917199088a3f5b4d2977c76ac190160d2ff1cddd7
6e3dc911ca9858c286ee0cdc50951da582baa8a790da9c37ea72f94475fbe5ba
36e3b87eb5257afac5f936458253e19d528a69f97f19e8fd91fb8d0478f4d5af
48c8f4416917c621bcede0132deab2c48bf095ede5baf9eda6824657996278aa
48a898c2d7c6ac6ca7339e50c4e95b804ff30b4f90bea3cbe434c2d3338e9801'''.split()
candidates = []
for h in hashes:
    data = (w / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    text = data.decode()
    item: dict[str, object] = dict(sha256=h, bytes=len(data))
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        item['format'] = 'non-JSON text'
        item['opening_nonempty_line'] = next((s[:160] for s in text.splitlines() if s.strip()), '')
    else:
        item['format'] = 'JSON'
        item['top_keys'] = list(value)[:15] if isinstance(value, dict) else ['list']
        if isinstance(value, dict) and 'resultList' in value:
            item['matched_article_metadata'] = [{k: r.get(k) for k in ['id', 'pmcid', 'title', 'isOpenAccess']}
                                                for r in value['resultList'].get('result', []) if r.get('pmcid') == 'PMC6623163']
        if isinstance(value, list):
            item['first_item_keys'] = list(value[0])[:15] if value and isinstance(value[0], dict) else []
    candidates.append(item)
print('CANDIDATES', json.dumps(candidates, indent=2))
(out / 'pmc6623163-candidate-inspection.json').write_text(json.dumps(candidates, indent=2))
peer = json.loads((q / 'inputs/peer-endpoint-artifact.json').read_text())
h = peer['output_blob']
peer_data = (w / 'blobs/sha256' / h[:2] / h).read_bytes()
assert sha(peer_data) == h
print('PEER OUTPUT', peer['manifest']['output']['name'])
print(peer_data.decode())
