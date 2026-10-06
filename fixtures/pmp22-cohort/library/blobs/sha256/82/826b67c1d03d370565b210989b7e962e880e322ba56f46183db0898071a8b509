"""Independent numerical, provenance and resource-consistency checks for this question."""
import csv,hashlib,json,os
from pathlib import Path
import numpy as np
from scipy import stats
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';O=Q/'outputs';myelin=json.loads((Q/'inputs/panel-spec.json').read_text())['panels']['myelin7'];checks=[]
def load(p):return json.loads(p.read_text(),parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
for name in ['screen-execution-r002','array-execution-r003','validation-execution-r001','robustness-execution-r001','rbp-coverage-execution-r002','resource-execution-r002']:
    r=load(O/f'{name}.json');assert r['exit_code']==0 and r['complete'] and r['code_unchanged'];assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest()==r['code_sha256']
    for item in r['outputs']:assert item['written'] and hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    checks.append({'check':name,'outputs':len(r['outputs']),'passed':True})
contrasts_checked=0
for stage in ['screen','array','validation']:
    summary=load(O/f'{stage}-summary.json');table=list(csv.DictReader((O/f'{stage}-sample-values.tsv').open(),delimiter='\t'))
    for r in summary['contrasts']:
        ds=r.get('dataset',summary.get('dataset'));name=r['contrast'];values={}
        for row in table:
            if stage!='validation' and (row['dataset']!=ds or row['contrast']!=name):continue
            s=row['sample'];g=row['gene'];value=float(row['normalized_value']) if stage=='array' else float(np.log2(float(row['cpm'])+.1))
            values.setdefault(s,{})[g]=value
        def score(s):return values[s]['Pmp22']-np.mean([values[s][g] for g in myelin])
        a=np.array([score(s) for s in r['control']]);b=np.array([score(s) for s in r['treated']]);actual=r.get('primary_selectivity',r.get('selectivity'));assert actual is not None
        np.testing.assert_allclose(b.mean()-a.mean(),actual['effect'],atol=1e-12,rtol=0)
        test=stats.ttest_rel(b,a) if r.get('paired') else stats.ttest_ind(b,a,equal_var=False)
        ci=test.confidence_interval(confidence_level=.95)
        np.testing.assert_allclose([ci.low,ci.high],[actual['ci_low'],actual['ci_high']],atol=1e-10,rtol=0)
        np.testing.assert_allclose(r['Pmp22']['effect']-r['myelin7']['effect'],actual['effect'],atol=1e-12,rtol=0)
        assert len(set(r['control']))==r['n_control'] and len(set(r['treated']))==r['n_treated'];contrasts_checked+=1
ranked=list(csv.DictReader((O/'ranked-candidates.tsv').open(),delimiter='\t'));resource=load(O/'contrast-resource-summary.json');assert len(ranked)==resource['contrast_rows'];assert resource['datasets']==len(set(r['dataset'] for r in ranked));assert len(ranked)==contrasts_checked+1
assert all(int(r['family_rank'])==4 for r in ranked if r['contrast'].startswith('raptorKO_vs') or r['contrast']=='genotype_by_injury')
v=load(O/'validation-summary.json');assert v['frozen_prediction_sha256']==hashlib.sha256((Q/'inputs/frozen-prediction.json').read_bytes()).hexdigest();assert v['selection_sha256']==hashlib.sha256((Q/'inputs/validation-selection.json').read_bytes()).hexdigest();assert v['primary_decision']=='magnitude_pass';assert v['contrasts'][0]['primary_selectivity']['exact_signflip_p']==.25
assert v['genotype_by_injury']['selectivity']['ci_low']>-.5 and v['genotype_by_injury']['selectivity']['ci_high']<.5
raw_validation=list(csv.DictReader((O/'validation-sample-values.tsv').open(),delimiter='\t'));vv={}
for row in raw_validation:vv.setdefault(row['sample'],{})[row['gene']]=float(np.log2(float(row['cpm'])+.1))
def relative(sample):return vv[sample]['Pmp22']-np.mean([vv[sample][g] for g in myelin])
control_changes=np.array([relative(f'Control{i}_crush')-relative(f'Control{i}_ctrlat') for i in [1,2,3]])
ko_changes=np.array([relative(f'KO{i}_crush')-relative(f'KO{i}_ctrlat') for i in [1,2,3]])
ci=stats.ttest_ind(ko_changes,control_changes,equal_var=False).confidence_interval(confidence_level=.95)
expected=v['genotype_by_injury']['selectivity']
np.testing.assert_allclose([ko_changes.mean()-control_changes.mean(),ci.low,ci.high],[expected['effect'],expected['ci_low'],expected['ci_high']],atol=1e-10,rtol=0)
annotation=load(O/'array-annotation-mismatches.json');assert len(annotation)==18 and all(r['native_name'] not in ['Pmp22',*myelin] for r in annotation)
for path in ['rbp-peer-manifest.json','promoter-peer-manifest.json']:
    x=load(O/path);assert 'manifest' in x and hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['output_blob']
    print('PEER_MANIFEST',path,'role',x.get('output_role'),'inputs',len(x['manifest']['derivation']['inputs']),'code_entries',len(x['manifest']['derivation']['code']),'output',x['output_blob'])
result={'passed':True,'producer_receipts':checks,'independently_recomputed_direct_contrasts':contrasts_checked,'independently_recomputed_interactions':1,'resource':resource,'checks':['target-minus-panel algebra','sample-level effects and scipy confidence intervals','paired-change interaction and scipy confidence interval','producer and output hashes','frozen lock hashes','source assay sample counts','ranked negative controls','unmatched annotation tokens retained outside target panels','peer immutable output integrity']}
(O/'final-validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
