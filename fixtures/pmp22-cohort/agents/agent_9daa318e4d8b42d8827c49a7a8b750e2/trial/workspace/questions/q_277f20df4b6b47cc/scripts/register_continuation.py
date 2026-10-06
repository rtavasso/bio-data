import pathlib,json,subprocess,sys
q=pathlib.Path(__file__).resolve().parents[1];root=q.parents[2];bio=str(root/'bin/bio');out=q/'outputs';ledger=out/'continuation-registration.json'
records=json.loads(ledger.read_text()) if ledger.exists() else {}
def call(args):
 p=subprocess.run([bio,*args],capture_output=True,text=True,check=True);return json.loads(p.stdout)
def obj(path):
 k=str(path.relative_to(q))
 z=call(['object','add',str(path)]);records.setdefault('inputs',{})[k]=z;ledger.write_text(json.dumps(records,indent=2));return z['blob']
def reg(name,script,inputs,role,extra_codes=None):
 if name in records.get('outputs',{}):return
 ii=[s if s.startswith(('asset_','artifact_')) else obj(q/s) for s in inputs]
 args=['register',str(out/name),'--question',q.name,'--title','PMP22 continuation: '+name,'--code',str(q/'scripts'/script),'--output-role',role,'--parameters',json.dumps({'analysis':'question-local executed script','source_semantics':'See companion summary; no missing-to-zero imputation'})]
 for i in ii:args+=['--input',i]
 for c in (extra_codes or []):args+=['--code',str(q/'scripts'/c)]
 r=call(args);records.setdefault('outputs',{})[name]=r;ledger.write_text(json.dumps(records,indent=2));print(name,r.get('artifact',r.get('id',r)))
if __name__=='__main__':
 group=sys.argv[1]
 if group=='rna':
  inp=['artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a','inputs/continued-reuse.json','inputs/continuation/GSE201623.soft']
  for name in ['rna-all-features.tsv','rna-audit-summary.json','rna-broad-extremes.tsv','rna-sample-correlations.tsv','rna-pca.tsv','rna-qc.png']:
   reg(name,'audit_rna_continued.py',inp,name.rsplit('.',1)[0])
 if group=='protein':
  inp=['inputs/continuation/PMC8191293-mmc2.xlsx','inputs/continuation/PMC8191293.xml','inputs/continuation/PXD023091-files.json']
  for name in ['protein-selected-interactors.tsv','protein-interactor-comparisons.tsv','protein-list-membership.tsv','protein-shared-ranked.tsv','protein-analysis-summary.json','protein-interactor-summary.png']:
   reg(name,'analyze_protein_interactors.py',inp,name.rsplit('.',1)[0])
 if group=='globin':
  parent=records['outputs']['rna-all-features.tsv'];print('parent',parent)
  aid=parent.get('artifact',parent.get('artifact_id',parent.get('id')))
  if aid is None:raise ValueError('inspect registration key')
  for name in ['rna-globin-followup.tsv','rna-globin-summary.json']:
   reg(name,'analyze_globin_followup.py',[aid,'inputs/continuation/GSE201623-counts-fresh.txt.gz','inputs/continued-rna-source.json','asset_5de0f13aed91ff279c9633dbded6a267'],name.rsplit('.',1)[0])

 if group=='more':
  rna=records['outputs']['rna-all-features.tsv']['artifact']
  for name in ['rna-hemoglobin-specific.tsv','rna-hemoglobin-summary.json']:
   reg(name,'analyze_globin_specific.py',[rna],name.rsplit('.',1)[0])
  human_inputs=['inputs/continuation/GSE7423-matrix.txt.gz','inputs/continuation/GPL1708.annot.gz','inputs/continuation/GSM178757-quick.soft']
  for name in ['human-dosage-all-probes.tsv','human-dosage-regulator-probes.tsv','human-dosage-technical-qc.tsv','human-dosage-broad-extremes.tsv','human-dosage-summary.json']:
   reg(name,'analyze_human_dosage.py',human_inputs,name.rsplit('.',1)[0])
  h=records['outputs']['human-dosage-all-probes.tsv']['artifact']
  for name in ['human-pmp22-channel-audit.tsv','human-channel-metadata.json','human-donor-correlations.tsv','human-contrast-correlations.tsv','human-channel-audit-summary.json']:
   reg(name,'audit_human_channels.py',[h]+['inputs/continuation/'+sid+'-full.soft' for sid in ['GSM178757','GSM178758','GSM178760','GSM178761','GSM178763']],name.rsplit('.',1)[0])
  for name in ['g3bp-half-life.tsv','g3bp-endpoint-summary.json']:
   reg(name,'analyze_g3bp_endpoints.py',['inputs/continuation/PMC3866477.xml','inputs/continuation/PMC3866477-1476-4598-12-156-S2.pdf','outputs/source-text/g3bp1-table.txt'],name.rsplit('.',1)[0],['read_pdf.swift'])
 if group=='atac':
  inp=['inputs/continuation/GSM3484775.tdf','inputs/continuation/GSM3484776.tdf','inputs/continuation/mm10-refGene.txt.gz','inputs/continuation/GSM3484775.soft','inputs/continuation/GSM3484776.soft','inputs/continuation/PMC6482019.xml','inputs/continuation/TDF-format.md']
  for name in ['runx-atac-all-promoters.tsv','runx-atac-regulator-loci.tsv','runx-atac-broad-extremes.tsv','runx-atac-signal-qc.tsv','runx-atac-summary.json']:
   reg(name,'analyze_runx_accessibility.py',inp,name.rsplit('.',1)[0],['read_tdf.py'])
