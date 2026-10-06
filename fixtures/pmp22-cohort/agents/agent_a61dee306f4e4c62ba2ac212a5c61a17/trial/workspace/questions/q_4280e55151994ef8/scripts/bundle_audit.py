"""Bundle only this question's selected sources, analyses and provenance; validate exact ZIP bytes."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'
exclude = {'stress-audit-bundle.zip','bundle-manifest.json','bundle-validation.json','bundle-registration.json','bundle-artifact-readback.json'}
files = [ROOT/'LABBOOK.md',ROOT/'QUESTION.md']
files += list((ROOT/'scripts').glob('*.py'))
files += [p for p in (ROOT/'inputs').rglob('*') if p.is_file() and p.suffix != '.html']
files += [p for p in OUT.iterdir() if p.is_file() and p.name not in exclude and not p.name.startswith('bundle-execution')]
manifest = []
for p in sorted(set(files)):
    data = p.read_bytes()
    manifest.append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(OUT/'bundle-manifest.json').write_text(json.dumps({'members':manifest,'scope':'Own question only; HTML challenge/error bodies remain local, exact receipt hashes retained; no inherited executable analysis imported'},indent=2,allow_nan=False)+'\n')
with zipfile.ZipFile(OUT/'stress-audit-bundle.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for row in manifest:
        z.write(ROOT/row['path'],row['path'])
    z.write(OUT/'bundle-manifest.json','bundle-manifest.json')
with zipfile.ZipFile(OUT/'stress-audit-bundle.zip') as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(manifest)+1
    for row in manifest:
        body = z.read(row['path'])
        assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
validation={'status':'passed','archive_members':len(manifest)+1,'verified_source_members':len(manifest),
            'zip_bytes':(OUT/'stress-audit-bundle.zip').stat().st_size,
            'zip_sha256':hashlib.sha256((OUT/'stress-audit-bundle.zip').read_bytes()).hexdigest(),
            'no_scientific_rerun':'Packaging only; original computational receipts inside archive'}
(OUT/'bundle-validation.json').write_text(json.dumps(validation,indent=2,allow_nan=False)+'\n')
print(json.dumps(validation))
