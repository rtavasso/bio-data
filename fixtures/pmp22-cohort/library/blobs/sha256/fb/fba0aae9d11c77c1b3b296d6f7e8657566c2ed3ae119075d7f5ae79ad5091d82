"""Compile curated source audit and extract real native tables; never fit unsupported rates."""
import csv
from decimal import Decimal
import gzip
import hashlib

import json
import os
from pathlib import Path
import re
from xml.etree import ElementTree as ET

q = Path(__file__).resolve().parents[1]
w = Path(os.environ['BIO_WORKSPACE'])
out = q / 'outputs'
out.mkdir(exist_ok=True)
manifest = json.loads((q / 'inputs/analysis-manifest-r003.json').read_text())
objects = {r['logical_path']:r for r in manifest['objects']}

def data(name):
    r = objects[name]
    p = w / 'blobs/sha256' / r['blob'][:2] / r['blob']
    b = p.read_bytes()
    assert hashlib.sha256(b).hexdigest() == r['blob']
    assert len(b) == r['bytes']
    return b

def js(name):
    return json.loads(data(name))

def dump(name, obj):
    (out / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')

def tsv(name, rows):
    assert rows
    with (out / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)

curated = js('inputs/curation.json')
assert len(set(r['id'] for r in curated['evidence'])) == len(curated['evidence'])
source_map = {}
for r in curated['evidence']:
    names = [f"inputs/primary/{r['source']}.{ext}" for ext in ['source','xml']]
    name = next(n for n in names if n in objects)
    root = ET.fromstring(data(name))
    source_map[r['source']] = {**objects[name], 'xml_root':root.tag}
    assert root.tag in ['article','collection']

# Exact table-cell extraction rather than digitization or fabricated replicate data.
tables = {}
for source, tableid in [('PMC2728407','tbl1'), ('PMC3866477','T1')]:
    root = ET.fromstring(data(source_map[source]['logical_path']))
    table = root.find(f".//table-wrap[@id='{tableid}']")
    assert table is not None
    rows = [[' '.join(''.join(c.itertext()).split()) for c in row if c.tag in ['td','th']] for row in table.findall('.//tr')]
    tables[source] = {'locator':tableid,'rows':rows,'source_blob':source_map[source]['blob']}
ire = next(r for r in tables['PMC2728407']['rows'] if any('(Pmp22)' in c for c in r))
assert ire[-1] == 'Yes'
rescued, knockout = [Decimal(v.replace('−','-')) for v in ire[-3:-1]]
assert rescued == Decimal('-0.88') and knockout == Decimal('-0.07')
difference = rescued - knockout
summaries = {
    'nature':'Retrospective arithmetic on published summary means; not a new biological test',
    'ire1':{'source_row':ire,'contrast':'log2(DTT/untreated) hIre1R minus log2(DTT/untreated) Ire1-null',
            'difference':float(difference),'confidence_interval':None,'reason_no_interval':'Replicate-level table values/covariance not provided',
            'inference':'IRE1-dependent stress response in fibroblast abundance; source stability assay separately supports faster loss. Not a measured half-life.'},
    'g3bp':{'half_lives':tables['PMC3866477']['rows'], 'inference':'Source reports no significant stability difference, not equivalence; no re-test from summary SEM'}
}
assert difference == Decimal('-0.81')

# Probe only the one actually acquired native SLAMseq processed sample.
b = data('inputs/native/GSM8792189.csv.gz')
lines = gzip.decompress(b).decode().splitlines()
assert lines[0] == '# name:siControl_DMSO_1'
reader = csv.DictReader(lines[1:], delimiter='\t')
assert reader.fieldnames == ['gene_name','length','readsCPM','conversionRate','Tcontent','coverageOnTs','conversionsOnTs','readCount','tcReadCount','multimapCount']
rows = list(reader)
assert all(None not in r for r in rows)
ids = [r['gene_name'] for r in rows]
for r in rows:
    n, tc = int(r['readCount']), int(r['tcReadCount'])
    assert 0 <= tc <= n
native = {'source':objects['inputs/native/GSM8792189.csv.gz'], 'sample':'GSM8792189','header':reader.fieldnames,
          'native_first_line':lines[0], 'rows':len(rows),'unique_feature_ids':len(set(ids)),
          'refseq_like_ids':sum(bool(re.fullmatch(r'[NX][MR]_\d+\.\d+', s)) for s in ids),
          'literal_PMP22_symbol_rows':ids.count('PMP22'), 'first_feature_ids':ids[:5],
          'assay':'Processed slamdunk total/T-C counts and conversion metrics; gzip TSV, despite .csv suffix',
          'PMP22_measured_status':'Unresolved without matching versioned feature annotation; literal symbol absence is not missing biology or zero',
          'analysis_performed':'Schema, row-count and count-range checks only; no PMP22 contrast, no rate fitting',
          'calibration':'No calibrated fraction-new or target-specific synthesis is inferred from conversionRate'}

# All series sample labels; bounded profile's detailed metadata may be incomplete.
samples = []
for series, bundle in [('GSE289482','bundle_34c53097b66a18c0797661f1'), ('GSE118660','bundle_14000f9ebab7cc60dec474f4')]:
    obj = js('inputs/geo/' + bundle + '.json')
    details = {x['native_id']:x['body']['fields'] for x in obj['profiles'][0]['facts']['related_source_context'] if x['kind']=='sample'}
    relations = [r for r in obj['relationships'] if r['relationship']=='contains_sample']
    for rel in relations:
        gsm = rel['locator'].removeprefix('^SAMPLE = ')
        f = details.get(gsm)
        samples.append({'series':series,'gsm':gsm,'snapshot':rel['snapshot_id'],
            'metadata_in_saved_profile':f is not None,'fields':f,'donor_id':None,
            'donor_status':'No donor identity assigned; cell-line experiment labels are not independent human donors',
            'selected_for_native_inspection':gsm=='GSM8792189',
            'source_exclusion':('Source reports siControl stress replicate3 PCA outlier; not independently replicated' if gsm=='GSM8792195' else None)})
assert len({s['gsm'] for s in samples}) == len(samples)
selected = js('inputs/geo/selected-files.json')
assert len(selected)==16
geo = {'samples':samples,'native_probe':native,'preliminary_selected_file_count':len(selected),'actually_acquired_native_samples':['GSM8792189'],
       'GSE289482_conflicts':[
          {'field':'tunicamycin duration','GEO':'4 hours','paper':'5 hours','resolution':None},
          {'field':'library preparation','GEO':'Lexogen QuantSeq 3-prime','paper_methods':'NEBNext poly(A) isolation + UltraII directional','paper_results':'3-prime library','resolution':None},
          {'field':'s4U concentration','GEO_and_paper_methods':'250 micromolar','paper_Figure3':'100 micromolar','resolution':None}],
       'eligibility':[
          {'series':'GSE289482','endpoint':'PMP22 route-specific decay','eligible':False,'blockers':['HCT116 not Schwann','No IRE1-RNase perturbation','Single pulse not pulse-chase','Timing/library conflicts','Native versioned target mapping unresolved','No matched target-specific translation measurement audited']},
          {'series':'GSE118660','endpoint':'PMP22 RNA/translation/decay decomposition','eligible':False,'blockers':['Total RNA-seq only in audited design','PERK WT/null MEF and NIH3T3 are distinct contexts','No documented same-sample RPF/chase','Do not join inherited footprints merely by stress label']}],
       'metadata_scope':'Detailed sample fields from bounded saved CLI profile, not a claim that unreturned public metadata do not exist'}

# Verify core curations against actual source text, not just hand-entered claims.
alltext = {k:re.sub(r'\s+', ' ', ''.join(ET.fromstring(data(v['logical_path'])).itertext())) for k,v in source_map.items()}
assert '7 nt seed' in alltext['PMC2713384-bioc']
assert '48 h post transfection' in alltext['PMC6920087']
assert '650 bp deletion' in alltext['PMC10545524']
assert 'siControl ER stress replicate 3' in alltext['PMC13431160']
assert '4 μg/ml' in alltext['PMC3866477']

curated['sources'] = source_map
curated['published_table_extraction'] = tables
curated['published_summary_calculation'] = summaries
curated['eligibility'] = geo
curated['input_manifest'] = manifest
curated['validation'] = {'source_hashes_checked':True,'finite_JSON':True,'table_row_assertions_passed':True,
                         'native_tc_within_total':True,'no_rate_fit':True,'synthetic_biological_measurements':False}
dump('rna-fate-audit.json',curated)
dump('sample-assay-eligibility.json',geo)
dump('published-measurements.json',{'tables':tables,'summary':summaries})
tsv('evidence-matrix.tsv',curated['evidence'])
tsv('assay-matrix.tsv',curated['assays'])
print(json.dumps({'evidence_rows':len(curated['evidence']),'assay_rows':len(curated['assays']),
                  'sample_labels':len(samples),'native_rows':len(rows),'ire1_published_log2_difference':float(difference),
                  'GSE289482_labels':sum(s['series']=='GSE289482' for s in samples),
                  'GSE289482_profile_details':sum(s['series']=='GSE289482' and s['metadata_in_saved_profile'] for s in samples),
                  'native_probe':native},allow_nan=False))
