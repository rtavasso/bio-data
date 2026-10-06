"""Retrieve narrow primary-literature searches with actual HTTP receipts."""
import json
from pathlib import Path
from urllib.parse import urlencode
from retrieve import retrieve
q = Path(__file__).resolve().parents[1]
queries = {
    'pum': '(PMP22 OR "peripheral myelin protein 22") AND (PUM1 OR PUM2 OR Pumilio)',
    'cnot': '(PMP22 OR "peripheral myelin protein 22") AND (CNOT1 OR CNOT7 OR CNOT8 OR "CCR4-NOT")',
    'qki': '(PMP22 OR "peripheral myelin protein 22") AND (QKI OR Quaking)',
}
results = []
for name, query in queries.items():
    label = 'novelty-focused-' + name + '-r001'
    rec = retrieve(label, 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urlencode({'query': query, 'format': 'json', 'pageSize': 100, 'resultType': 'core'}))
    assert rec['complete'] and rec['status'] == 200
    data = json.loads((q/'inputs/http'/(label+'.payload')).read_text())
    hits = [{'id': x.get('id'), 'pmcid': x.get('pmcid'), 'title': x.get('title'), 'year': x.get('pubYear'), 'abstract': x.get('abstractText')} for x in data['resultList']['result']]
    results.append({'query': query, 'receipt': label, 'hitCount': data['hitCount'], 'returned': len(hits), 'hits': hits})
    print(name, data['hitCount'], [(x['id'], x['pmcid'], x['title']) for x in hits])
(q/'outputs/novelty-focused-r001.json').write_text(json.dumps(results, indent=2, allow_nan=False))
