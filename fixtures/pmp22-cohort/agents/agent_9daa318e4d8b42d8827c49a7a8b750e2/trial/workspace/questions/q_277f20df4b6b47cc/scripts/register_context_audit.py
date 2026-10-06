from pathlib import Path
import subprocess,json,hashlib
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';root=Q.parents[2];B=root/'bin/bio';qid=Q.name
receipts=json.loads((O/'registrations.json').read_text()) if (O/'registrations.json').exists() else [];objects={}
def call(args):
 p=subprocess.run([str(B)]+[str(a) for a in args],cwd=root,capture_output=True,text=True)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return json.loads(p.stdout)
def obj(p):
 r=call(['object','add',p]);objects[str(p.relative_to(Q))]=r;return r['blob']
def register(script,names,inputs,params):
 for n in names:
  if any(x['file']==n for x in receipts):continue
  args=['register',O/n,'--question',qid,'--title','PMP22 context audit: '+n,'--output-role','context-audit-'+n.replace('.','-'),'--code',Q/'scripts'/script,'--parameters',json.dumps(params)]
  for i in inputs:args+=['--input',i]
  r=call(args);receipts.append(dict(file=n,script=script,receipt=r));(O/'registrations.json').write_text(json.dumps(receipts,indent=2)+'\n')
  print(n,r['artifact'])
meta=[obj(Q/'inputs/iteration/GSE118660-samples.soft'),obj(Q/'inputs/iteration/PMC6416471.xml')]
a='7740f1a5d816fd8a98a17e67e6c6621ca438c5afd14addb62309f9148f3c6dc7';b='8b837d3c0a48e869522484f68d0837994ee9c932e2dac52ef6dd5f679b6928d7';s='37583638e8e9aec98b62feb7749e0d8446113914a2733dd8986051b549b6da01'
register('analyze_footprint_context.py',['shared-gene-effects.tsv','reference-sensitivity.tsv','reference-members.tsv','summary-r001.json','context-comparison.png'],[a,b]+meta,dict(scope='retrospective descriptive shared2h and secondary8vs7h',baseline_floor=[4,10,20],primary_match='both controls within +/-1log2',biological_n=1))
register('analyze_footprint_followup.py',['source-cluster-memberships.tsv','normalization-invariance.json','floor-program-sensitivity.tsv','genotype-all-trajectories.tsv','genotype-reference-summary.tsv','genotype-controls.tsv','followup-summary.json'],[a,b,s]+meta,dict(scope='retrospective clipping/program/genotype tests',floor=4,baseline=10,match='box1 and nearest250'))
ridd=obj(Q/'inputs/context-audit/PMC2728407.xml')
register('analyze_ridd_source.py',['ridd-source-table-effects.tsv','ridd-array-methods.txt','ridd-summary.json'],[ridd],dict(scope='known-result source TableI extraction',selector='all26selectedrows',stressor='2mMDTT6h',units='reportedmeanlog2'))
# These outputs are exactly those consumed by the final script; use registered artifacts, not invented source-only provenance.
byname={x['file']:x['receipt']['artifact'] for x in receipts}
print('ids',byname)
assert all(byname.values())
register('analyze_context_classes.py',['ridd-reference-eligibility.tsv','ridd-footprint-context.tsv','late-cluster-baseline-matched-members.tsv','late-cluster-axis-ranks.tsv','class-comparison-summary.json'],[byname[n] for n in ['shared-gene-effects.tsv','source-cluster-memberships.tsv','ridd-source-table-effects.tsv']],dict(scope='reduced exact-symbolRIDDpanel and posthoclateclusteraxisranks',mapping='literalTableIsymbols only',baseline=10))
(O/'input-objects.json').write_text(json.dumps(objects,indent=2)+'\n')

byname={x['file']:x['receipt']['artifact'] for x in receipts}
register('analyze_footprint_counts.py',['counts-all-effects.tsv','counts-primary-source.tsv','counts-reference-summary.tsv','counts-summary.json'],['14ca149475bf0716e53a54775c0519d6f111deb5a41e17db368a4633de9a0169','asset_53dd40f9b97a2571a2fb2632ea636cab',byname['shared-gene-effects.tsv']],dict(scope='same-library count-versus-TPM check',reference='fixed1276TPMmatchedgenes',normalizations=['CPM','median_ratio']))
byname={x['file']:x['receipt']['artifact'] for x in receipts}
register('plot_context_summary.py',['context-summary-r002.png','context-summary-r002.pdf'],[byname[n] for n in ['shared-gene-effects.tsv','late-cluster-baseline-matched-members.tsv','followup-summary.json','counts-reference-summary.tsv','summary-r001.json']],dict(scope='descriptive summary figure',version=2))
