from pathlib import Path
import json,subprocess,sys,hashlib
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2];O=Q/'outputs/specific';ledger=O/'registrations.json';R=json.loads(ledger.read_text()) if ledger.exists() else {'inputs':{},'outputs':{}}
def call(args):
 r=subprocess.run([str(ROOT/'bin/bio')]+args,capture_output=True,text=True,check=True);return json.loads(r.stdout)
def obj(rel):
 p=Q/rel;h=hashlib.sha256(p.read_bytes()).hexdigest()
 if rel not in R['inputs'] or R['inputs'][rel]['blob']!=h:R['inputs'][rel]=call(['object','add',str(p)])
 ledger.write_text(json.dumps(R,indent=2));return R['inputs'][rel]['blob']
def register(name,script,inputs,codes=[]):
 if name in R['outputs']:return
 ins=[i if i.startswith(('asset_','artifact_')) else obj(i) for i in inputs]
 args=['register',str(O/name),'--question',Q.name,'--title','PMP22 specificity: '+name,'--code',str(Q/'scripts'/script),'--output-role','specific-'+name.rsplit('.',1)[0],'--parameters',json.dumps({'script':'question-local '+script,'prediction_lock':'r002 where relevant','source_semantics':'See linked summary; missing values not zero imputed'})]
 for i in ins:args+=['--input',i]
 for c in codes:args+=['--code',str(Q/'scripts'/c)]
 R['outputs'][name]=call(args);ledger.write_text(json.dumps(R,indent=2));print(name,R['outputs'][name].get('artifact'))
if __name__=='__main__':
 group=sys.argv[1]
 if group=='discovery':
  ins=['asset_6000db4681916cb0f3f259855be2ebae','artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a','inputs/specific/fetch-discovery.json','inputs/specific/reuse-show.json','inputs/metadata-GSE177037-specific.json']
  for n in ['discovery-summary.json','discovery-all-gene-screen.tsv','discovery-selected.tsv','discovery-samples.tsv','discovery-feature-map.tsv','discovery-log2CPM.tsv']:register(n,'discover_specific.py',ins)
 if group=='integrity':
  register('eed-source-integrity.json','reseal_specific.py',['asset_759e58feea1124f2567a8508b27ca754','inputs/specific/fetch-validation.json','inputs/specific/GSE106969-alternate.csv.gz','outputs/specific/prediction-r001.json'])
 if group=='validation':
  ins=['outputs/specific/prediction-r002.json']+['inputs/specific/'+n for n in ['GSM1972986.soft','GSE76027_series_matrix.txt.gz','GPL13730.soft','Mus_musculus.gene_info.gz','metadata-GSE76027.json','metadata-GSE93159.json']]
  for k in ['cnp-ctrl','cnp-ko','dhh-ctrl','dhh-ko']:
   p='inputs/specific/fetch-hdac3-'+k+'.json';ins += [p,json.loads((Q/p).read_text())['asset_revision']]
  for n in ['validation-summary.json','validation-primary-results.tsv','validation-all-contexts.tsv','validation-array-mapping.tsv','zeb2-log2-expression.tsv','zeb2-samples.tsv','hdac3-FPKM.tsv','zeb2-sample-correlations.tsv','zeb2-PCA.tsv','zeb2-all-gene-effects.tsv']:register(n,'validate_specific.py',ins)
 if group=='alternatives':
  names=['discovery-log2CPM.tsv','zeb2-log2-expression.tsv','hdac3-FPKM.tsv','discovery-all-gene-screen.tsv'];ins=[R['outputs'][n]['artifact'] for n in names]+['outputs/specific/prediction-r002.json','asset_6000db4681916cb0f3f259855be2ebae','inputs/specific/fetch-discovery.json']
  for key in ['cnp-ctrl','cnp-ko','dhh-ctrl','dhh-ko']:
   rel=f'inputs/specific/fetch-hdac3-{key}.json';ins += [rel,json.loads((Q/rel).read_text())['asset_revision']]
  for n in ['familiar-regulator-comparison.tsv','compartment-enrichment.tsv','confounder-adjustment.tsv','marker-sensitivity.tsv','alternate-myelin-targets.tsv','hdac3-native-panel.tsv','hdac3-pseudocount-sensitivity.tsv','perturbation-biological-panel.tsv','alternatives-summary.json']:register(n,'check_specific_alternatives.py',ins)
 if group=='status':
  ins=[R['outputs'][n]['artifact'] for n in ['validation-summary.json','marker-sensitivity.tsv']]+['inputs/specific/cufflinks-file-formats.html']
  for key in ['cnp-ctrl','cnp-ko','dhh-ctrl','dhh-ko']:
   rel=f'inputs/specific/fetch-hdac3-{key}.json';ins += [rel,json.loads((Q/rel).read_text())['asset_revision']]
  for n in ['hdac3-status-audit.tsv','hdac3-eligible-FPKM.tsv','validation-summary-r003.json','six-marker-exploratory-transfer.tsv','correction-r003.json']:register(n,'audit_specific_status.py',ins)
 if group=='models':
  inherited=json.loads((Q/'outputs/continuation-registration.json').read_text())['outputs']
  ins=[R['outputs'][n]['artifact'] for n in ['discovery-log2CPM.tsv','zeb2-log2-expression.tsv']]+[inherited[n]['artifact'] for n in ['rna-all-features.tsv','runx-rna-all-features.tsv']]+['outputs/specific/prediction-r002.json']
  for n in ['nonlinear-baseline-comparison.tsv','nonlinear-baseline-predictions.tsv','inherited-retrospective-transfer.tsv','inherited-retrospective-panel.tsv','model-diagnostics-summary.json']:register(n,'diagnose_specific_models.py',ins)
 if group=='rnaseq-diagnostic':
  rel='inputs/specific/fetch-zeb2-rnaseq-diff.json';ins=[rel,json.loads((Q/rel).read_text())['asset_revision'],R['outputs']['discovery-log2CPM.tsv']['artifact'],'inputs/specific/metadata-GSE74381.json']
  for n in ['zeb2-rnaseq-native-panel.tsv','zeb2-rnaseq-diagnostic.tsv','zeb2-rnaseq-diagnostic-summary.json']:register(n,'diagnose_zeb2_rnaseq.py',ins)
 if group=='literature':
  ins=['inputs/specific/'+n for n in ['PMC9063194.xml','PMC4964942.xml','PMC4961522.html','PMC2440619.html','PMC6289291.html','cufflinks-file-formats.html']]+[str(p.relative_to(Q)) for p in (Q/'inputs/specific').glob('novelty-*.json')]
  for n in ['primary-literature-passages.json','novelty-abstracts.json','novelty-search-audit.json','literature-novelty-audit.json']:register(n,'audit_specific_literature.py',ins)
 if group=='representations':
  ins=['inputs/specific/metadata-GSE74381.json',R['outputs']['zeb2-rnaseq-native-panel.tsv']['artifact'],R['outputs']['discovery-log2CPM.tsv']['artifact']]
  for key in ['control','ko']:
   rel=f'inputs/specific/fetch-zeb2-rnaseq-{key}.json';ins += [rel,json.loads((Q/rel).read_text())['asset_revision']]
  for n in ['zeb2-rnaseq-transcript-source-panel.tsv','zeb2-representation-comparison.tsv','zeb2-single-file-pair-diagnostic.tsv','zeb2-representation-audit.json']:register(n,'audit_zeb2_representations.py',ins)
 if group=='robustness':
  ins=[R['outputs'][n]['artifact'] for n in ['discovery-log2CPM.tsv','zeb2-log2-expression.tsv']]
  for n in ['sample-leverage.tsv','array-dynamic-range-panel.tsv','robustness-summary.json']:register(n,'audit_specific_robustness.py',ins)
 if group=='figure':
  ins=[R['outputs'][n]['artifact'] for n in ['discovery-samples.tsv','discovery-selected.tsv','validation-primary-results.tsv','alternate-myelin-targets.tsv']]
  for n in ['PMP22-specificity.png','PMP22-specificity.pdf']:register(n,'plot_specific.py',ins)
 if group=='synthesis':
  ins=['outputs/specific/registrations-at-synthesis.json']+[R['outputs'][n]['artifact'] for n in ['discovery-summary.json','validation-summary-r003.json','robustness-summary.json','literature-novelty-audit.json']]+['outputs/discoveries.r001.json','outputs/mechanisms.r011.json','outputs/investigations.r009.json','outputs/evidence-coverage.pre-specific.tsv','outputs/specific/prediction-r002.json']
  register('RESULTS.json','finalize_specific.py',ins)
