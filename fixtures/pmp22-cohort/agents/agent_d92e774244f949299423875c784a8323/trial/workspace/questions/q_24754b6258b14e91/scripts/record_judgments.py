"""Record scoped scientific judgments with exact existing artifact and prediction references."""
import hashlib
import json
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
idx={x['file']:x['artifact'] for x in json.loads((Q/'outputs/registrations-final/index.json').read_text())}
base={'revision':1,'scope':'Human PMP22 GTEx v11 regulatory associations and two independent-cohort validation attempts.',
 'known_baseline':'Public cis-expression/splicing QTLs and source SuSiE results already exist. Human reporter/UTR mechanisms are prior work; see inputs/human-interval-annotations.json and LABBOOK.md.',
 'budget_allocation':'Scientific effort covered all 50 GTEx tissues, source annotations, full GENCORD universe and independent TwinsUK export; no configured time/request cap or reserve breach. No endless resampling of selected hits.',
 'stopping_reason':'The bounded summary-statistic questions are answered: first-exon-linked discovery, failed fibroblast significance prediction, untestable exact splice replication and explicit native coverage. Further causal/cell-type claims require new compatible data; public all-pairs and source-specific filtering gaps retained.',
 'candidates':[],'no_candidates_reason':''}
novelty={'status':'known','closest_prior_work':[{'source':'GTEx v11 official native QTL summary downloads',
 'locator':'inputs/public/gtex-openfiles.json and README_eQTL_v11.txt',
 'relationship':'Associations and fine mapping are source-produced public findings; this audit harmonizes and tests their transfer rather than discovering a causal mechanism.'}],
 'searches':[{'query':'PMP22 AND (eQTL OR sQTL)','date':'2026-10-05','evidence':'inputs/public/novelty-focused.json'},
             {'query':'rs231016','date':'2026-10-05','evidence':'inputs/public/novelty-rs231016.json'}],
 'limitation':'Scoped searches, not exhaustive novelty certification. No indexed SNP paper does not make a public GTEx row novel.'}
for cid,claim,status,mode,result,context,nexttest in [
 ('fibroblast-cis-transfer','The leading GTEx fibroblast eQTL direction transfers significantly to independent GENCORD fibroblasts.',
  'unresolved','prospective','The frozen p<.05 and positive-direction rule failed: beta+.0800765, SE.0908986, p.379585. Direction agrees, interval wide; no equivalence or biological heterogeneity established.',
  'GTEx adult cultured fibroblast RNA versus186 GENCORD newborn cord-derived fibroblasts; exact rs2531950 A>G.',
  'Test the same allele in a well-powered independent adult-fibroblast cohort before endogenous regulatory-region perturbation.'),
 ('adipose-first-exon-junction-transfer','The rs231016 alternative-first-exon-linked junction association transfers to independent adipose.',
  'candidate','not_tested','GTEx q=.00149858 and seven-variant source credible set support discovery; exact TwinsUK replication was untestable. Different acceptor15260757 is not substituted for15260761.',
  'GTEx bulk subcutaneous adipose; chr17:15260761:15265154 minus junction; independent TwinsUK exact-feature coverage insufficient.',
  'Recover independent all-tested exact-junction statistics; then separate nascent initiation from splicing/stability in allele-matched cells.')]:
    rel=f'outputs/predictions/{cid}-r001.json'
    h=hashlib.sha256((Q/rel).read_bytes()).hexdigest()
    base['candidates'].append({'id':cid,'claim':claim,'context':context,'kind':'biological','status':status,
     'alternatives':['Cis RNA processing/stability versus initiation','Context/composition or culture differences','LD-tagged regulatory or structural variation','Power/selection/annotation effects'],
     'discovery_artifacts':[idx['tested-feature-summary.json'],idx['source-credible-sets.tsv']],
     'prediction_lock':rel,'prediction_sha256':h,'validation_mode':mode,'validation_artifacts':[idx['independent-evidence.json']],
     'validation_result':result,'independence_assessment':'Cohorts distinct; current Catalogue primary paper describes unrelated TwinsUK subset. Different GTEx tissues/releases and Catalogue reanalysis not independent. Source counts not manufactured donors.',
     'novelty':novelty,'limitations':'No promoter initiation, causal nucleotide, Schwann specificity or protein output. Source normalized scales differ; do not pool effects.',
     'next_test':nexttest})
with (Q/'outputs/discoveries.json').open('x') as f:json.dump(base,f,indent=2,allow_nan=False)
print('Recorded',len(base['candidates']),'candidate judgments')
