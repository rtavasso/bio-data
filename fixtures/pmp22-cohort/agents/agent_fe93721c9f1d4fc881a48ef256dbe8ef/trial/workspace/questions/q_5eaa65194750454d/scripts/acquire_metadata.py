"""Native metadata and acquisition: use exact asset revisions returned by bio."""
import json
import subprocess
from pathlib import Path
q = Path(__file__).resolve().parents[1]

def cli(name, args):
    p = subprocess.run(['./bin/bio', *args], capture_output=True, text=True)
    (q/'outputs'/f'{name}.json').write_text(p.stdout)
    if p.returncode:
        (q/'outputs'/f'{name}.stderr').write_text(p.stderr)
        print('FAILED', name, p.stdout, p.stderr)
        return None
    return json.loads(p.stdout)

for label in ['hdac3-homeostatic','nedd4','ptp4a1','hdac-class2']:
    d = json.loads((q/f'outputs/{label}-source.json').read_text())
    r = d['profiles'][0]['facts']['source_record']
    print('PRIMARY_META', label, {k:r.get(k) for k in ['id','pmcid','doi','title','dataLinksTagsList','fullTextUrlList']})
for label in ['nae1-rna','selectivity']:
    d = json.loads((q/f'outputs/{label}-manifest.json').read_text())
    print('INPUTS', label, d['manifest']['derivation']['inputs'])
for pmc in ['PMC10959528','PMC3100536']:
    d = cli(pmc+'-resolve', ['resolve', pmc,'--provider','europepmc'])
    if d:
        a = cli(pmc+'-assets', ['data','list','--scope',d['bundle'],'--limit','50'])
        print('ASSETS', pmc, a)
print('INCOMING', cli('incoming-critique', ['community','show','post_29739839562f46f1af2524a2588cb10e']))
