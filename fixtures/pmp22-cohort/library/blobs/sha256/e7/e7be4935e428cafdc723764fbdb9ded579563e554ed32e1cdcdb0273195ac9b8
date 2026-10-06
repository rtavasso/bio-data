"""Independent checks of native tokens, all response estimates and output bytes."""
import csv
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from PIL import Image

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'

def load(name):
    with (OUT/name).open() as f:
        return list(csv.DictReader(f, delimiter='\t'))

checks = []

def check(ok, name):
    assert ok, name
    checks.append(name)


def close(actual, expected):
    return actual == 'NA' if expected is None else math.isclose(float(actual),expected,rel_tol=1e-10,abs_tol=1e-10)

receipt = json.loads((OUT/'execution-r002.json').read_text())
check(receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged'], 'producer_receipt_complete')
check(hashlib.sha256((Q/'scripts/analyze_responses.py').read_bytes()).hexdigest()==receipt['code_sha256'], 'executed_code_is_current')
for output in receipt['outputs']:
    p = OUT/Path(output['path']).name
    check(output['written'] and hashlib.sha256(p.read_bytes()).hexdigest()==output['sha256'], 'producer_output_hash_'+p.name)
manifest = json.loads((Q/'sources/immutable-inputs.json').read_text())
for label in ['native','mapping','samples']:
    check(hashlib.sha256((Q/manifest[label]['path']).read_bytes()).hexdigest()==manifest[label]['sha256'], 'input_hash_'+label)
with (Q/manifest['native']['path']).open() as f:
    reader = csv.DictReader(f,delimiter='\t')
    columns = [c for c in reader.fieldnames if c.endswith(' RPM')]
    original = {r['TSS id']:r for r in reader}
check(len(original)==4993 and len(columns)==14, 'native_dimensions')
for r in load('pmp22-native-rows.tsv'):
    check(all(v == original[r['TSS id']][k] for k,v in r.items() if k!='native_line'), 'source_tokens_'+r['TSS id'])
check(len(load('pmp22-native-rows.tsv'))==22, 'pmp22_all22_retained')

samples = load('sample-design.tsv')
check(len(samples)==14 and len({s['accession'] for s in samples})==14, 'unique_libraries')
check(all(s['donor_id']=='NA' and s['treatment_pair_id']=='NA' for s in samples), 'no_invented_donor_pairing')
groups = {g:[s['native_column'] for s in samples if s['condition']==g] for g in {s['condition'] for s in samples}}
contrasts = {'cAMP_vs_vehicle':(groups['primary_control'],groups['primary_cAMP']),
             'SOX10_KO_vs_parental':(groups['S16_parental'],groups['S16_SOX10_KO'])}
summary = json.loads((OUT/'summary.json').read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
sets = summary['sets']
# Re-derive positional membership directly from native tokens, not the producer's membership table.
for name, pair in sets.items():
    for p, ids in pair.items():
        focal_id = '5439' if p=='P1' else '5446'
        f = original[focal_id]
        expected = [focal_id] if name=='focal' else [cid for cid,r in original.items() if r['Gene Symbol']=='Pmp22' and r['TSS Chr']==f['TSS Chr'] and r['TSS Strand']==f['TSS Strand'] and abs((int(r['TSS Start'])+int(r['TSS End'])-int(f['TSS Start'])-int(f['TSS End']))/2)<=int(name.split('_')[1])]
        check(ids==expected, 'membership_'+name+'_'+p)

# Verify the reused mapping anchors in the actual saved rn5 sequence.
seq = json.loads((Q/'sources/inputs/rn5-Pmp22-promoter-sequence.json').read_text())
with (Q/manifest['mapping']['path']).open() as f:
    maps = list(csv.DictReader(f,delimiter='\t'))
for m in maps:
    offset = int(m['primer_start_0based'])-seq['start']
    primer = m['forward_primer']
    check(seq['dna'].upper()[offset:offset+len(primer)]==primer, 'primer_anchor_'+m['promoter_label'])
    check(seq['dna'].upper().count(primer)==1, 'primer_local_unique_'+m['promoter_label'])


def val(name, promoter, c, method, constant):
    x = sum(Decimal(original[cid][c]) for cid in sets[name][promoter])
    return float(x+Decimal(str(constant)) if method=='add' else max(x,Decimal(str(constant))) if method=='floor' else x)


def avg(v):
    return sum(v)/len(v)


def lr(a,b):
    return math.log(a/b,2) if a>0 and b>0 else None

for table in ['contrasts-and-sensitivity.tsv','leave-one-library.tsv','clone-family-contrasts.tsv']:
    rr = load(table)
    for row in rr:
        contrast = row.get('contrast','SOX10_KO_vs_parental')
        cc,tt = [list(x) for x in contrasts[contrast]]
        if 'omitted_library' in row:
            cc = [c for c in cc if c != row['omitted_library']]
            tt = [c for c in tt if c != row['omitted_library']]
        if 'clone_label_family' in row:
            tt = [c for c in tt if c.split('delSOX10 ')[1].split('-')[0]==row['clone_label_family']]
        vv = {c:[val(row['set'],p,c,row['method'],float(row['constant_RPM'])) for p in ['P1','P2']] for c in cc+tt}
        cm,tm = [[avg([vv[c][i] for c in group]) for i in [0,1]] for group in [cc,tt]]
        lfc = [lr(tm[i],cm[i]) for i in [0,1]]
        ratios = [[lr(*vv[c]) for c in group] for group in [cc,tt]]
        dlr = avg(ratios[1])-avg(ratios[0]) if all(r is not None for v in ratios for r in v) else None
        expected = {'P1_control_mean_RPM':cm[0], 'P2_control_mean_RPM':cm[1],
                    'P1_treated_mean_RPM':tm[0], 'P2_treated_mean_RPM':tm[1],
                    'P1_minus_P2_log2_fold_of_means':lfc[0]-lfc[1] if all(v is not None for v in lfc) else None,
                    'change_mean_log2_P1_P2':dlr,
                    'control_mean_P1_fraction':avg([vv[c][0]/sum(vv[c]) for c in cc]),
                    'treated_mean_P1_fraction':avg([vv[c][0]/sum(vv[c]) for c in tt])}
        assert all(close(row[k],v) for k,v in expected.items()), (table,row,expected)
    check(True,'decimal_recompute_'+table+'_'+str(len(rr)))

for row in load('per-library-start-signals.tsv'):
    c = row['native_column']
    a,b = [val(row['set'],p,c,'none',0) for p in ['P1','P2']]
    check(close(row['P1_RPM'],a) and close(row['P2_RPM'],b) and close(row['log2_P1_P2'],lr(a,b)), 'library_values_'+row['set']+'_'+row['accession'])

for table in ['comparator-contrasts.tsv','comparator-per-library.tsv']:
    for row in load(table):
        ids = row['member_ids'].split(',')
        if table=='comparator-per-library.tsv':
            expected = sum(float(original[i][row['native_column']]) for i in ids)
            assert close(row['RPM'],expected)
        else:
            cc,tt = contrasts[row['contrast']]
            vv = {c:sum(float(original[i][c]) for i in ids) for c in cc+tt}
            k = float(row['constant_RPM'])
            vv = {c:v+k if row['method']=='add' else max(v,k) if row['method']=='floor' else v for c,v in vv.items()}
            cm,tm = avg([vv[c] for c in cc]),avg([vv[c] for c in tt])
            assert close(row['control_mean_RPM'],cm) and close(row['treated_mean_RPM'],tm) and close(row['log2_fold_of_means'],lr(tm,cm))
    check(True,'comparator_recompute_'+table)

for name in ['focal-library-responses.png','robustness-grid.png','comparator-responses.png']:
    with Image.open(OUT/name) as image:
        check(image.width>=1000 and image.height>=800 and image.convert('L').getextrema()[0]<100, 'nonblank_figure_'+name)

check(summary['primary_contrasts'][0]['change_mean_log2_P1_P2'] is None, 'zero_not_silently_dropped_from_logratio')
check(summary['primary_contrasts'][1]['change_mean_log2_P1_P2'] < 0, 'SOX10_ratio_direction')
result = {'checks_passed':len(checks),'checks':checks,'source':manifest['native']['sha256'],
          'independent_validation':'Direct native-token/Decimal recomputation; not import of producer or independent biological replication',
          'producer_receipt_sha256':hashlib.sha256((OUT/'execution-r002.json').read_bytes()).hexdigest()}
(OUT/'validation.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps({'checks_passed':len(checks),'status':'PASS','validated_execution':'execution-r002.json'}))
