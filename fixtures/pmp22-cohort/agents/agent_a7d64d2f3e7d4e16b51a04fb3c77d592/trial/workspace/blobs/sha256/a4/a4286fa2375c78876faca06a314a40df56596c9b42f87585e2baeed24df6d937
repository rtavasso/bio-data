"""Register actual produced outputs, with source bytes, code and producing receipts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
REG = OUT/'registration'
REG.mkdir(exist_ok=True)
CACHE = {}


def run(args):
    p = subprocess.run(['./bin/bio',*args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stdout+'\n'+p.stderr)
    return json.loads(p.stdout)


def add(path):
    path = Path(path)
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    if h not in CACHE:
        r = run(['object','add',str(path),'--classification','reference'])
        assert r['blob'] == h
        CACHE[h] = r
    return h


def register(name, code, receipt_name, inputs):
    path = OUT/name
    receipt = json.loads((OUT/receipt_name).read_text())
    assert receipt['complete'] and receipt['exit_code'] == 0 and receipt['code_unchanged']
    assert hashlib.sha256((Q/'scripts'/code).read_bytes()).hexdigest() == receipt['code_sha256']
    original = next(x for x in receipt['outputs'] if Path(x['path']).name == name)
    assert original['written'] and hashlib.sha256(path.read_bytes()).hexdigest() == original['sha256']
    args = ['register',str(path),'--question',Q.name,'--title','PMP22 lipid-feedback: '+name,
            '--code',str(Q/'scripts'/code),'--reference',add(OUT/receipt_name),'--output-role',name.replace('.','-'),
            '--parameters',json.dumps({'scope':'exploratory quantitative candidate-feedback analysis','biological_replication':False,'source_paper_outcomes_exposed':True})]
    for source in sorted(set(inputs)):
        args.extend(['--input',source])
    r = run(args)
    (REG/(name+'.json')).write_text(json.dumps(r,indent=2))
    aid = r['artifact']
    readback = run(['artifact','show',aid])
    (REG/(name+'.readback.json')).write_text(json.dumps(readback,indent=2))
    assert readback['output_blob'] == original['sha256']
    print(name, aid, original['sha256'])
    return aid


rna_inputs = ['asset_eb583216ca5d57d46d6709cac42e2491','asset_87e1bda107d5f5034c7e020ee6b5c7f0',add(Q/'inputs/analysis-plan.json')]
for name in ['Acly-acquired.json','CMT-acquired.json','Acly-fetch.json','CMT-fetch.json']:
    rna_inputs.append(add(OUT/name))
if len(sys.argv)>1 and sys.argv[1]=='first':
    register('rna-program-contrasts.tsv','analyze_rna.py','rna-execution-r001.json',rna_inputs)
else:
    program_id = json.loads((REG/'rna-program-contrasts.tsv.json').read_text())['artifact']
    sample_id = register('rna-per-sample.tsv','analyze_rna.py','rna-execution-r001.json',rna_inputs)
    register('rna-all-gene-contrasts.tsv.gz','analyze_rna.py','rna-execution-r001.json',rna_inputs)
    peer_inputs = json.loads((OUT/'peer-input-inventory.json').read_text())
    validation_inputs = [sample_id,'artifact_2ecfb28855342b9e22f37d7d1255c2a5898b91246ac231bdd658600fab11105e',
                         add(OUT/'peer-input-inventory.json'),add(OUT/'predictions/abca1-abcg1-state-transfer-r001.json')]+[x['blob'] for x in peer_inputs]
    validate_id = register('validation-transfer.json','validate_transfer.py','transfer-execution-r001.json',validation_inputs)
    assembly_inputs = [program_id,validate_id,add(Q/'inputs/interpretation-curation.json')]
    for name in ['discovery-transporter-split.tsv','source-contrast-map.tsv','test-results-r002.txt','lint-results-r002.txt',
                 'rna-execution-r001.json','rna-summary-execution-r001.json','transfer-execution-r001.json']:
        assembly_inputs.append(add(OUT/name))
    analysis_id = register('candidate-feedback-analysis.json','build_delivery.py','delivery-execution-r001.json',assembly_inputs)
    manifest = json.loads((OUT/'source-provenance.json').read_text())
    # These exact member bytes were consumed by the assembler; registering them does not execute them.
    import zipfile
    with zipfile.ZipFile(OUT/'lipid-feedback-evidence.zip') as z:
        for item in manifest['files']:
            h = item['sha256']
            b = z.read(item['member'])
            assert hashlib.sha256(b).hexdigest()==h
            if h not in CACHE:
                staged = REG/'inputs'/h
                staged.parent.mkdir(exist_ok=True)
                if not staged.exists():
                    staged.write_bytes(b)
                assembly_inputs.append(add(staged))
            else:
                assembly_inputs.append(h)
    assembly_inputs.extend([analysis_id,'artifact_77331014c88a4d8da77add923216f59ec27fca413c2645732f895b484c172088',add(OUT/'artifact_77331014c88a4d8da77add923216f59ec27fca413c2645732f895b484c172088.json')])
    register('source-provenance.json','build_delivery.py','delivery-execution-r001.json',assembly_inputs)
    register('lipid-feedback-evidence.zip','build_delivery.py','delivery-execution-r001.json',assembly_inputs+[add(OUT/'source-provenance.json')])
(REG/'object-registration-cache.json').write_text(json.dumps(CACHE,indent=2))
