"""Save structured literature searches with actual HTTP receipts for novelty/validation discovery."""
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode
ROOT = Path(__file__).resolve().parents[1]
queries = {
    'novelty-specific-cargos': '(TITLE_ABS:ACSL5 OR TITLE_ABS:FACL5 OR TITLE_ABS:FCF1 OR TITLE_ABS:ERVFRD) AND (TITLE_ABS:secretion OR TITLE_ABS:trafficking)',
    'novelty-specific-pmp': 'TITLE_ABS:PMP22 AND (TITLE_ABS:ACSL5 OR TITLE_ABS:FCF1 OR TITLE_ABS:ERVFRD OR TITLE_ABS:GPR161 OR TITLE_ABS:TMEM220 OR TITLE_ABS:VU0494372)',
    'novelty-pmp-candidates': 'PMP22 AND (ACSL5 OR FACL5 OR FCF1 OR ERVFRD OR GPR161 OR TMEM220 OR VU0494372)',
    'validation-general-screen': '("Genome-wide RNAi" OR "genome wide RNAi") AND (secretion OR "secretory pathway" OR "protein transport")',
    'candidate-secretion': '(ACSL5 OR FACL5 OR FCF1 OR ERVFRD) AND (secretion OR trafficking OR "Golgi")',
    'candidate-acsl5-er': 'ACSL5 AND ("endoplasmic reticulum" OR "protein secretion")',
}
for name, query in queries.items():
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urlencode({'query': query, 'format': 'json', 'pageSize': 100, 'resultType': 'core'})
    path = ROOT / 'inputs/public' / (name + '.json')
    if not path.exists():
        subprocess.run(['./bin/python', str(ROOT/'scripts/acquire.py'), path.name, url], check=True)
    data = json.loads(path.read_text())
    print(name, 'query=',query, 'hitCount',data.get('hitCount'))
    for r in data.get('resultList',{}).get('result',[]):
        print(r.get('id'),r.get('pmcid'),r.get('title'),r.get('doi'))
