"""Generate official stable-ID symbol lookup URLs from the frozen panel, no recalled IDs."""
import json,os,urllib.parse
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'inputs/panel-spec.json').read_text());genes=list(dict.fromkeys(['Pmp22',*sum(x['panels'].values(),[])]))
urls={f'ensembl-mouse-{g}.json':'https://rest.ensembl.org/lookup/symbol/mus_musculus/'+urllib.parse.quote(g)+'?content-type=application/json' for g in genes}
(q/'inputs/mouse-symbol-urls.json').write_text(json.dumps(urls,indent=2));print('EXACT_SYMBOLS',genes)
