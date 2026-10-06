"""Register only verified products with exact code, inputs, receipts and readbacks."""
import hashlib
import json
import subprocess
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'


def call(args):
    r=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def preserve(path):
    return call(['object','add',str(path)])['blob']


def verify_receipt(name):
    p=OUT/name
    r=json.loads(p.read_text())
    assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
    assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest()==r['code_sha256']
    for o in r['outputs']:
        assert hashlib.sha256(Path(o['path']).read_bytes()).hexdigest()==o['sha256']
    return preserve(p)

refs={name:verify_receipt(name) for name in ['execution-r002.json','followup-execution-r002.json','tead-execution-r001.json','compile-execution-r001.json','sensitivity-execution-r001.json','bundle-execution-r001.json']}
plan=preserve(Q/'inputs/analysis-plan.r001.json')
followplan=preserve(Q/'inputs/followup-plan.r001.json')
registered=[]


def register(file,producer,inputs,references,title,summary,role):
    args=['register',str(OUT/file),'--question',Q.name,'--title',title,'--summary',summary,
          '--output-role',role,'--code',str(Q/'scripts'/producer),'--environment',str(OUT/'analysis-environment.json'),
          '--parameters',json.dumps({'version':1,'relative_not_absolute_abundance':True,'gene_scores_are_not_TF_activity':True,'source_units_not_pooled':True})]
    for h in sorted(set(inputs)):
        args.extend(['--input',h])
    for h in sorted(set(references)):
        args.extend(['--reference',h])
    r=call(args)
    (OUT/('registration-'+role+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    assert not r['conflicting_outputs']
    expected=hashlib.sha256((OUT/file).read_bytes()).hexdigest()
    assert r['output_blob']==expected
    b=call(['artifact','show',r['artifact']])
    (OUT/('readback-'+role+'.json')).write_text(json.dumps(b,indent=2)+'\n')
    assert b['output_blob']==expected and Q.name in json.dumps(b['questions'])
    registered.append({'file':file,'role':role,'artifact':r['artifact'],'output_blob':expected,'verified':True})
    return r['artifact']

main_inputs=list(json.loads((OUT/'executed-contrasts.json').read_text())['input_blobs'])
follow_inputs=list(json.loads((OUT/'followup-contrasts.json').read_text())['input_blobs'])
register('executed-contrasts.json','analyze_upstream.py',main_inputs+[plan],[refs['execution-r002.json']],
         'Upstream RNA-program contrasts: Nae1, Tsc1, Pten, Raptor, NRG1',
         'Five executed contrasts with preserved native units, feature floors, covariance-preserving program-minus-regulator contrasts, intervals and sensitivities. Raptor Egr2 nondepletion; Sox10 unresolved. Not direct activity.', 'initial-rna-contrasts')
register('followup-contrasts.json','analyze_followup.py',follow_inputs+[plan,followplan],[refs['followup-execution-r002.json']],
         'Nedd4 RNA preservation and RNF40 chromatin challenge',
         'Nedd4 both RNAs within +/-0.5 log2 bounds, modest heterogeneous myelin decline; RNF40 retains Egr2 but loses Sox10. Both stronger frozen pattern tests fail. Native gene table/counts with blank-row and metadata-conflict audits.', 'followup-rna-contrasts')
protein_inputs=[preserve(Q/f'inputs/tead-numeric/{g} prism file.pzfx') for g in ['Krox20','MPZ','MBP','Oct6']]
register('tead-protein-contrasts.json','analyze_tead.py',protein_inputs+['b75588038e125423341aac189ef322b832d5dad37ea9b73272ec7f0c1191ed2a','11c2558cb6e86ddacce2abf86289f86e1dd8981edb4d08db18849d7cca14031c'],[refs['tead-execution-r001.json']],
         'TEAD1 source protein reanalysis: Krox20 high, MPZ/MBP low',
         'Numeric Prism Table-only parsing; four protein endpoints from three mice/genotype. Independent assay subedge, not RNA preservation or PMP22 measurement; known biology reproduced.', 'tead-protein')
compile_inputs=[preserve(OUT/name) for name in ['executed-contrasts.json','followup-contrasts.json','sample-expression.tsv','followup-sample-expression.tsv']]+[plan]
for file,role in [('integrated-contrasts.tsv','integrated-rna-table'),('ranked-upstream-candidates.tsv','ranked-candidates')]:
    register(file,'compile_results.py',compile_inputs,[refs['compile-execution-r001.json'],refs['execution-r002.json'],refs['followup-execution-r002.json'],refs['tead-execution-r001.json']],
             'Upstream RNA-program investigation: '+role,
             'Seven RNA contrasts and ranked orthogonal TEAD1 candidate; fixed PMP22-excluded output proxy, meaningful preservation bounds, conditional source-unit intervals. No novel causal regulator claimed.',role)
register('preservation-sensitivity.json','analyze_sensitivity.py',compile_inputs,[refs['sensitivity-execution-r001.json']],
         'Fourteen-regulator preservation-bound sensitivity',
         'Post-hoc Bonferroni intervals over Egr2/Sox10 across seven RNA contrasts. Nedd4 both intervals remain within +/-0.5; does not resolve bulk composition or source-unit independence.', 'preservation-sensitivity')
manifest= json.loads((OUT/'bundle-manifest.json').read_text())
bundle_inputs=manifest['native_blobs']+[preserve(OUT/'bundle-manifest.json'),preserve(OUT/'REPORT.md'),preserve(OUT/'bundle-replay-verification.json')]
register('bundle-upstream-activity.zip','pack_replay.py',bundle_inputs,[refs['bundle-execution-r001.json'],*refs.values()],
         'Upstream RNA-program reproducibility bundle: seven RNA contrasts, TEAD1 protein and bounds',
         'Standalone native-source bundle with code, measurements, eligibility, ranked candidates, source audit and failures. Fresh isolated local replay reproduced six TSV files byte-for-byte and three scientific JSON products after input-path normalization.', 'reproducibility-bundle')
(OUT/'registrations.json').write_text(json.dumps(registered,indent=2)+'\n')
print(json.dumps(registered,indent=2))
