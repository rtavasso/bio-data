import json,pathlib,subprocess,hashlib
q=pathlib.Path(__file__).resolve().parents[1]; qid=q.name
def bio(*args):return json.loads(subprocess.check_output(['bio',*map(str,args)]))
ledger={}
for p in sorted((q/'inputs').glob('*.json')):
 ledger[str(p.relative_to(q))]=bio('object','add',p)['blob']
for p in sorted((q/'outputs').glob('*')):
 if p.suffix in ['.json','.md','.tsv','.txt'] and p.name!='preservation.json':
  ledger[str(p.relative_to(q))]=bio('object','add',p,'--classification','interpretation' if p.name.startswith('mechanisms') or p.suffix=='.md' or p.name=='evidence-coverage.tsv' else 'data')['blob']
# Conservatively include every metadata file actually opened by a script, as well as source identities.
specs=[
('inspect_local.py',['asset_f7b45493c97bcbf69f884f50fb111ee5','asset_cdf8b8e076f450328f72d80a5b95ff92','asset_5e0d2a886bec03b7d7670bd5d9197dc6','asset_df4a5bbba7882ab8aee56ef2591274bb'],['tss-regulatory-panel.tsv','local-source-extraction.json','PMC7430845-paragraphs.txt']),
('analyze_rna.py',['artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a'],['egr2-as-regulatory-panel.tsv','rna-normalization.json']),
('analyze_atac.py',['asset_c3bc524f6b0d57c01d1709dec24cf801','asset_5d646466456220a089ff8e65ff2dd2a6','asset_5af4bd06c28c3f88d7b4cde500f161bd','asset_dbbd6e785b9997688f2be7d6ace37d76','asset_b59cf55f51237ff92b69d16a70bdb77d'],['atac-promoter-overlaps.tsv','atac-promoter-summary.tsv','atac-method.json'])
]
regs=[]
for script,ids,outputs in specs:
 for name in outputs:
  args=['register',q/'outputs'/name,'--question',qid,'--title',f'PMP22 regulatory system: {name}','--code',q/'scripts'/script,'--parameters',json.dumps({'method':'See preserved script; descriptive source-specific extraction/analysis','script':script})]
  for a in ids: args+=['--input',a,'--input',ledger[f'inputs/{a}.json']]
  regs.append(bio(*args)); print(name,regs[-1].get('artifact',regs[-1].get('id')))
(q/'outputs/preservation.json').write_text(json.dumps({'objects':ledger,'registrations':regs},indent=2))
with open(q/'LABBOOK.md','a') as f:
 f.write('\n## Preserved objects and registered computations\n\n')
 for p,h in ledger.items():
  if p.startswith('outputs/mechanisms') or p.endswith('evidence-coverage.tsv') or p.endswith('REPORT.md'):f.write(f'- {p}: {h}\n')
 f.write('\nAll input metadata and output hashes plus registration receipts: outputs/preservation.json. Agent-authored prose/maps are immutable interpretation objects, not fabricated computational artifacts. Computed outputs registered with scripts, source IDs and metadata-file hashes.\n')
