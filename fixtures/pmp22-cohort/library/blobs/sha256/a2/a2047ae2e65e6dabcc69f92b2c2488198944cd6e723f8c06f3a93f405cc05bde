"""Register only verified producer outputs, with exact input bytes and readback."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy
import openpyxl
import pandas
import scipy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
S=ROOT/'inputs'/'sources'
REG=OUT/'registrations'
REG.mkdir(exist_ok=True)
config=tomllib.loads((Path(os.environ['BIO_WORKSPACE'])/'config.toml').read_text())['budgets']
cachepath=REG/'stored-inputs.json'
cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}

def call(*args):
    result=subprocess.run(['./bin/bio',*map(str,args)],text=True,capture_output=True)
    if result.returncode:
        print(result.stdout,result.stderr,file=sys.stderr)
        result.check_returncode()
    return json.loads(result.stdout)

def store(path):
    path=Path(path)
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    key=str(path)
    if key not in cache or cache[key]['blob']!=h:
        disk=shutil.disk_usage(ROOT)
        assert disk.free-path.stat().st_size>max(config['reserve_bytes'],config['reserve_fraction']*disk.total)
        value=call('object','add',path)
        assert value['blob']==h
        actual=call('object','show',h)
        assert hashlib.sha256(Path(actual['path']).read_bytes()).hexdigest()==h
        cache[key]=value
        cachepath.write_text(json.dumps(cache,indent=2)+'\n')
    return h

groups=[
 ('numeric-audit-execution-r001.json',[OUT/'GSE65778-paper-constituent-counts.tsv.gz',OUT/'GSE65778-full-native-counts.tsv.gz'],'Separate exact-identifier absence from numeric disagreement; native uc002goj.2 RNA and uc002goj.3 RPF reproduce all source-table PMP22 counts without asserting sequence equivalence'),
 ('arsenite-execution-r003.json',[S/f'GSM{i}' for i in range(1331342,1331350)]+[ROOT/'inputs'/'analysis-plan-r001.json',S/'GSE55195.soft',S/'PMC4383229.xml'],'HEK293T arsenite 40 uM 30 min, matched RNA/RPF, n=2 per condition; relative occupancy, not flux'),
 ('isrib-execution-r003.json',[S/f'GSM{i}' for i in range(1606099,1606115)]+[S/'GSE65778.soft',S/'elife05033s001.xlsx',S/'PMC4341466.xml',ROOT/'inputs'/'analysis-plan-r001.json',ROOT/'inputs'/'independent-context-prediction-r001.json',ROOT/'inputs'/'representation-amendment-r001.txt'],'HEK293T tunicamycin 1 ug/ml 1 h +/- ISRIB 200 nM; source-paper paired count matrix, n=2 per condition; GEO export equivalence failed; RNA selection unresolved'),
 ('secondary-audit-execution-r003.json',[S/'elife05033s001.xlsx',OUT/'GSE65778-full-native-counts.tsv.gz',OUT/'GSE65778-full-native-lengths.tsv.gz'],'Exact source-paper versus per-GSM export audit; missing identifiers never imputed'),
 ('novelty-execution-r002.json',[S/n for n in ['PMC4383229.xml','PMC4341466.xml','PMC12807861.xml','GSE55195-supp','elife05033s001.xlsx','elife05033s002.xlsx','GSE256237-S2']]+[OUT/'GSE65778-full-native-counts.tsv.gz',OUT/'novelty-discovery.json'],'Scoped source-paper and supplementary-table novelty audit; structured literature records retained in output, not all search hits read'),
 ('design-execution-r005.json',[S/n for n in ['GSE256237.soft','GSE256237-counts','hgnc-complete.tsv','GSE256237-S2','GSM1331342']],'Calibrated HCT116 route: PMP22 absent from deposited processed universe; absence is not measured zero'),
 ('validation-execution-r001.json',[OUT/n for n in ['GSE55195-effects.json','GSE65778-effects.json','GSE65778-paper-constituent-counts.tsv.gz','GSE65778-feature-map.tsv','GSE65778-full-background-effects.tsv.gz','GSE65778-controls.tsv']],'Independent arithmetic and scipy Welch verification plus baseline RNA/RPF-count-matched background sensitivity')]
env={'python':platform.python_version(),'numpy':numpy.__version__,'pandas':pandas.__version__,'scipy':scipy.__version__,'openpyxl':openpyxl.__version__}
index=[]
for receipt_name,deps,summary in groups:
    receipt=OUT/receipt_name
    executed=json.loads(receipt.read_text())
    code=Path(executed['producer'])
    assert executed['complete'] and executed['exit_code']==0
    assert hashlib.sha256(code.read_bytes()).hexdigest()==executed['code_sha256']
    inputs=[]
    for dep in deps+[receipt]:
        item={'blob':store(dep),'role':'execution-receipt' if dep==receipt else 'input-or-source-context','selector':{'question_relative_path':str(dep.relative_to(ROOT))}}
        fetched=OUT/('fetch-'+dep.name+'.json')
        if dep.parent==S and fetched.exists():
            acquired=json.loads(fetched.read_text())
            assert acquired['blob']==item['blob']
            item['source_identity']=acquired['asset_revision']
        inputs.append(item)
        if dep.parent==S:
            for transport in sorted(S.glob(dep.name+'.*.receipt.json')):
                inputs.append({'blob':store(transport),'role':'transport-receipt','selector':{'question_relative_path':str(transport.relative_to(ROOT))}})
            if fetched.exists():
                inputs.append({'blob':store(fetched),'role':'acquisition-receipt','selector':{'question_relative_path':str(fetched.relative_to(ROOT))}})
    derivation={'inputs':inputs,'code':[store(code)],'command':executed['argv'],'parameters':{'execution_receipt':store(receipt),'question':'q_7e888aba063b4092','interpretation':summary},'references':[store(S/'PMC4383229.xml'),store(S/'PMC4341466.xml')],'environment':env}
    for output in executed['outputs']:
        path=Path(output['path'])
        assert output['written'] and hashlib.sha256(path.read_bytes()).hexdigest()==output['sha256']
        saved=REG/(path.name+'.registration.json')
        if not saved.exists():
            manifest={'title':path.name,'summary':summary,'derivation':derivation,'output_role':path.name,'limitations':['Biological n=2 in each analyzed condition; broad small-sample uncertainty','Relative assay composition only; no absolute protein-production flux or Schwann-cell transfer','Alternative representations and reruns are not biological replication']}
            mp=REG/(path.name+'.manifest.json')
            if mp.exists():
                store(mp)
            mp.write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
            value=call('register',path,'--question','q_7e888aba063b4092','--manifest',mp)
            saved.write_text(json.dumps(value,indent=2)+'\n')
            assert value['output_blob']==output['sha256']
            readback=call('artifact','show',value['artifact'])
            assert readback['output_blob']==value['output_blob']
            assert readback['manifest']['derivation']['code']==derivation['code']
            (REG/(path.name+'.readback.json')).write_text(json.dumps(readback,indent=2)+'\n')
            print(json.dumps(value),flush=True)
            if '--one' in sys.argv:
                raise SystemExit(0)
        value=json.loads(saved.read_text())
        assert value['output_blob']==output['sha256']
        index.append({'file':path.name,'artifact':value['artifact'],'output_blob':value['output_blob'],'producer_receipt':receipt_name})
(OUT/'artifact-index.json').write_text(json.dumps(index,indent=2)+'\n')
print(json.dumps(index,indent=2))
