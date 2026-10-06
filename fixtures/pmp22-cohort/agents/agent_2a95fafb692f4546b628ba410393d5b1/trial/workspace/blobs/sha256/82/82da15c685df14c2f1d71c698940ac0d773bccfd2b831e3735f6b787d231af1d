"""Checkpoint selected analysis and fetch only indexed processed RNA representations."""
from pathlib import Path
import json,subprocess,datetime
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2];I=Q/'inputs/upstream';O=Q/'outputs/upstream';BIO=str(ROOT/'bin/bio')
def cli(args):
 r=subprocess.run([BIO,*args],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout+r.stderr)
 return json.loads(r.stdout)
x=json.loads((Q/'outputs/investigations.json').read_text());x['revision']=25
it=x['items'][-1];it.update(status='ready',assets=['GSE241269','PXD043917','PMC11014456'],question='Does inherited Pmp22 relative RNA preservation transfer to independent Nae1 loss; can orthogonal proteomics distinguish post-transcriptional effects?',readout='P7 4+4 RSEM RNA; processed mzIdentML protein metadata/quantitation eligibility',finding='Primary source supplies multiple upstream non-transcriptional mechanisms, not a direct PMP22 outcome; protein age and species/software metadata conflict.',limitation='Protein Fig7 P7 versus Methods/PRIDE P15, PRIDE rat and MaxQuant versus mouse/PEAKS; no matched proteome inference without source resolution.',next_action='Run sealed RNA transfer and complete broad RNA exploration; inspect processed mzIdentML for quantitative eligibility.',decision='outputs/upstream/prediction-r001.json')
for id,question,assets,evidence,limit in [
 ('qki-splicing-export','Can human QKI perturbation separate PMP22 total RNA from alternative transcript usage?',['PMC13234107'],['inputs/upstream/PMC13234107.xml','inputs/upstream/receipts/QKI-supplements.zip.json','inputs/upstream/receipts/QKI-supplement-pmc.pdf.json'],'Source data upon request; linked public supplement PDF, no deposited expression/splice-event matrix. Alternative archive HTTP500, PMC PDF returned HTML; published target directions already exposed.'),
 ('fdft1-perturbation-export','Does cholesterol synthesis loss change PMP22 beyond a generic differentiation response?',['PMC13042600'],['inputs/upstream/PMC13042600.xml','outputs/upstream/FDFT1-data-inventory.json','inputs/upstream/ADVS-13-e20323-s002.docx'],'Native data archive contains images/STR PDFs only; supplement contains figures/reagents/primers, not full RNA matrix; upon-request data statement. Target absence from selected displays not absence of measurement.')]:
 x['items'].append(dict(id=id,priority='high',question=question,alternatives=['direct or selective target regulation','broader differentiation program'],readout='Full processed per-sample matrix with quality and sample annotation',assets=assets,prerequisites=['Full event/gene universe; independent sample identities'],status='blocked',artifacts=[],finding='Source and linked supplements inspected; quantitative prerequisite missing.',limitation=limit,next_action='Obtain public full processed export or author-supplied matrix; no contact sent.',blocker_evidence=evidence))
(Q/'outputs/investigations.json').write_text(json.dumps(x,indent=2)+'\n');(Q/'outputs/investigations.r025.json').write_text(json.dumps(x,indent=2)+'\n')
m=json.loads((Q/'outputs/mechanisms.json').read_text());m['revision']=19;m['nodes'].append(dict(id='neddylation',label='NAE1-dependent neddylation',kind='upstream protein modification'))
m['edges'].append(dict(id='neddylation-egr2-stability',source='neddylation',target='egr',mechanism='Supports EGR2 protein persistence; MLN4924 destabilizes EGR2 under myelinogenic conditions',context='Primary rat Schwann cultures and mouse developmental Nae1 cKO; direct modified residue not mapped',status='supported',evidence=[dict(source='PMC11014456',locator='Results Neddylation stabilizes EGR2 protein; Fig8 K-M; outputs/upstream/PMC11014456-text.txt lines69-76',basis='CHX decay, NEDD8-associated capture and increased ubiquitination; not a direct PMP22 protein half-life experiment')]))
m['frontier'].append(dict(node='neddylation',question='Does Pmp22 depart from the general myelin RNA/protein response after Nae1 loss?',priority='high',reason='Orthogonal source located; RNA count transfer sealed before outcomes, proteome source identity conflicts need inspection.',status='open'))
m['changes'].append(dict(reason='Indirect mechanism/assay discovery adds upstream modification of regulator protein persistence. Known source result, no new mechanistic credit. RNA/protein context discrepancies prevented a paired-effect plan.',evidence=[dict(source='PMC11014456;PXD043917;GSE241269',locator='outputs/upstream/NEDD-metadata-review.txt',basis='P7 RNA versus P15 proteomics protocol and unresolved species/software fields; choose valid RNA analysis and inspect protein eligibility.')]))
for p in [Q/'outputs/mechanisms.json',Q/'outputs/mechanisms.r019.json']:p.write_text(json.dumps(m,indent=2)+'\n')
rec=[]
for p in [Q/'outputs/investigations.r025.json',Q/'outputs/mechanisms.r019.json']:rec.append(dict(path=str(p.relative_to(Q)),receipt=cli(['object','add',str(p),'--classification','interpretation'])))
(O/'checkpoint-r003-receipts.json').write_text(json.dumps(rec,indent=2))
seal=json.loads((O/'prediction-seal-receipt.json').read_text())
with (Q/'LABBOOK.md').open('a') as f:f.write('\n## Upstream selected-analysis checkpoint\nNeddylation source chosen over unreplicated TSC1 and blocked QKI/FDFT1 matrices. Source P7/P15 and PRIDE species/software discrepancies prevent a matched RNA-protein mechanistic contrast. Sealed independent RNA transfer of inherited relative-preservation hypothesis before target outcomes: '+json.dumps(seal)+'. Queue r025/map r019 preserved; checkpoint-r003 receipts. Initial hand-authored browser accounting was corrected: actual discovery is direct EPMC/bio, with receipts; no unsupported browser outcome retained.\n')
assets=json.loads((I/'GSE241269-assets.json').read_text())['items'];receipts=[]
for a in assets:
 if a['name'].endswith('.genes.results.gz'):
  r=cli(['fetch',a['asset_revision'],'--question',Q.name]);p=I/(a['name']+'.fetch.json');p.write_text(json.dumps(r,indent=2));receipts.append(dict(name=a['name'],receipt=r));print(a['name'],json.dumps(r))
(I/'rna-fetch-receipts.json').write_text(json.dumps(receipts,indent=2))
# Generate selected RESULT download manifest from preserved native inventory only.
f=[f for f in json.loads((I/'PXD043917-files-r002.json').read_text()) if f['fileCategory']['value']=='RESULT']
tasks=[]
for a in f:
 u=next(v['value'] for v in a['publicFileLocations'] if v['name']=='FTP Protocol').replace('ftp://','https://',1);tasks.append(dict(name=a['fileName'],url=u))
(I/'acquire-r008.json').write_text(json.dumps(tasks,indent=2));print('protein selected',tasks)
