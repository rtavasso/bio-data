"""Read existing PMID metadata/receipts; no new retrieval or scientific processing."""
import hashlib
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
p = q / 'sources/primary'
source = p / 'pmp22-cis-nascent-search.json'
receipt = json.loads((p / 'pmp22-cis-nascent-search.json.receipt.json').read_text())
assert hashlib.sha256(source.read_bytes()).hexdigest() == receipt['sha256']
records = json.loads(source.read_text())['resultList']['result']
matched = [r for r in records if r.get('id') == '42801440']
assert len(matched) == 1
record = matched[0]
print('EXACT_SELECTOR resultList.result WHERE id == "42801440", abstractText')
print('TITLE', record['title'])
print('ABSTRACT', record['abstractText'].replace('<h4>', '\n').replace('</h4>', '\n'))
print('RECEIPT', json.dumps(receipt, indent=2))
publisher = p / 'PMID42801440-publisher.html'
pub_receipt = json.loads((p / (publisher.name + '.receipt.json')).read_text())
assert hashlib.sha256(publisher.read_bytes()).hexdigest() == pub_receipt['sha256']
assert '<title>Client Challenge</title>' in publisher.read_text()
print('PUBLISHER_RECEIPT', json.dumps(pub_receipt, indent=2))
manifest = json.loads((q / 'sources/immutable-inputs.json').read_text())
aggregate_path = q / 'sources/transport-receipts.json'
aggregate = json.loads(aggregate_path.read_text())
assert hashlib.sha256(aggregate_path.read_bytes()).hexdigest() == manifest['transport-receipts.json']['blob']
for name in ('pmp22-cis-nascent-search.json.receipt.json', 'PMID42801440-publisher.html.receipt.json'):
    entry = [r for r in aggregate if r['relative_path'] == 'primary/' + name]
    assert len(entry) == 1
    assert entry[0]['original_text'] == (p / name).read_text()
    assert hashlib.sha256((p / name).read_bytes()).hexdigest() == entry[0]['sha256']
print('VERIFIED_IMMUTABLE_RECEIPT_AGGREGATE', manifest['transport-receipts.json']['blob'])
for term in ('tata', 'dosage'):
    result = json.loads((q / f'sources/community/{term}-human-followup-search.json').read_text())
    assert result.get('next_offset') is None
    print('FORUM', term, 'RESULTS', len(result['items']))
    for item in result['items']:
        print(item['subject'], item['title'], item.get('superseded_by', []))
