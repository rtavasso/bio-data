"""Build a selective evidence handoff with explicit omissions; verify every included byte."""
import hashlib
import json
from pathlib import Path
import zipfile
Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
selected=set()
def add(p):
    if p.is_file():selected.add(p)
for folder in ['outputs/final-r002','outputs/independent-r002','outputs/predictions']:
    for p in (Q/folder).iterdir():add(p)
for name in ['ranked-followup.md','discoveries.json','inspection-v11.json','peer-end-site-map.tsv']:
    add(OUT/name)
for p in OUT.glob('*execution*.json*'):
    if not p.name.startswith('package-execution'):
        add(p)
for name in ['harmonize_qtl.py','extract_independent.py','inspect_native.py','query_tabix.py','map_features.py',
             'retrieve.py','remote_tar.py','fetch_inventory.py','resume_gencord.py','register_final.py','record_judgments.py']:
    add(Q/'scripts'/name)
for name in ['LABBOOK.md','inputs/human-interval-annotations.json','inputs/text/pmp22-gencode47.json']:
    add(Q/name)
for name in ['gtex-openfiles.json','README_eQTL_v11.txt','catalogue-metadata-r7.tsv','catalogue-methods.html',
             'catalogue-columns.md','PMC8423625.xml','PMC3673336.xml','PMC3100536-bioc.xml',
             'twins-primary-bioc.xml','hg18ToHg38.over.chain.gz','chain-format.html','novelty-focused.json',
             'novelty-rs231016.json','QTD000100.permuted.tsv.gz','QTD000538.permuted.tsv.gz',
             'gtex-datasets.json','gtex-nominal-prefix-list.json','catalogue-tabix-paths.tsv',
             'gencord-files.html','twins-leafcutter-files.html']:
    add(Q/'inputs/public'/name)
for p in (Q/'inputs/public').glob('*.receipt.json'):add(p)
for p in (Q/'inputs/reused-cis').iterdir():add(p)
for name in ['cis-answer-r001.json','rna-answer.json','rbp-current.json','rna-end-artifact-r002.json',
             'rna-end-fetch-r002.json','rna-handoff-retry.json','cis-source-artifact.json']:
    add(Q/'inputs/community'/name)
for name in ['QTD000100-15314994-all','QTD000538-15263668-cc']:
    for p in (Q/'inputs/ranges'/name).iterdir():add(p)
for assay in ['eqtl','sqtl']:
    for tissue in ['Nerve_Tibial','Cells_Cultured_fibroblasts','Adipose_Subcutaneous','Ovary']:
        for p in (Q/f'inputs/native/v11-{assay}').glob(f'{tissue}*.txt.gz*'):add(p)
    add(Q/f'inputs/ranges/v11-{assay}/inventory.json')
# Numerical products must still match actual successful producing receipt.
rec=json.loads((OUT/'final-execution-r002.json').read_text())
assert rec['complete'] and rec['exit_code']==0 and rec['code_unchanged']
for x in rec['outputs']:
    assert hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256']
assert hashlib.sha256((Q/'scripts/harmonize_qtl.py').read_bytes()).hexdigest()==rec['code_sha256']
rows=[{'path':str(p.relative_to(Q)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
      for p in sorted(selected)]
manifest={'format':'selective native/source/derived handoff','members':rows,'producer_receipt':'outputs/final-execution-r002.json',
 'exclusions':'Whole-cohort3.48GB GENCORD source, incomplete prior download, whole TwinsUK .cc, full GENCODE GTF, full GTEx parquet/tar response bodies are omitted. Registered final derivations retain exact immutable input blobs; selected target tables and sources/receipts here are not a complete raw-source closure. No downloaded source code is executed.',
 'ledger_note':'record_judgments.py authored revision1; revision2 manually corrected untestable coverage classification only. Earlier ledger preserved as blob039ec7cec73f6c626b844dd87fce1b60163ef845df28db1dbb987d5a46efb379.',
 'prior_analysis_artifacts':json.loads((OUT/'registrations-final/index.json').read_text())}
mp=OUT/'handoff-manifest-r002.json'
with mp.open('x') as f:json.dump(manifest,f,indent=2,allow_nan=False)
zp=OUT/'pmp22-regulatory-qtl-handoff-r002.zip'
with zipfile.ZipFile(zp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(selected):z.write(p,str(p.relative_to(Q)))
    z.write(mp,'handoff-manifest.json')
with zipfile.ZipFile(zp) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(rows)+1
    for r in rows:
        b=z.read(r['path']);assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
validation={'zip_bytes':zp.stat().st_size,'zip_sha256':hashlib.sha256(zp.read_bytes()).hexdigest(),
            'member_count_including_manifest':len(rows)+1,'all_member_hashes_sizes_crc_passed':True,
            'scientific_reanalysis':False,'purpose':'Selective byte-preserving transport package'}
with (OUT/'handoff-validation-r002.json').open('x') as f:json.dump(validation,f,indent=2)
print(json.dumps(validation))
