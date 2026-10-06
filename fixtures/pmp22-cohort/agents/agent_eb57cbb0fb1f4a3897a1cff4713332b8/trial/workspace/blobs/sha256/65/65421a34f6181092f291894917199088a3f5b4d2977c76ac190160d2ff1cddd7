"""Compact primary-source audit and exact result digest for reporting."""
from pathlib import Path
import json,re,datetime
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/upstream';I=Q/'inputs/upstream'
summary=json.loads((O/'antioxidant-posthoc-summary.json').read_text())
for r in summary['panels']:print(r['study'],r['panel'],round(r['effect'],4),[round(v,4) for v in r['ci95']])
print('BROAD',json.dumps(summary['broad'],indent=2))
passages=[]
patterns={'PMC5802790':r'LXR.*(PMP22|Nrf2)|PMP22.*(promoter|LXR)|N-acetylcysteine|[^a-z]NAC[^a-z]|agonist|Data avail', 'PMC6944556':r'PMP22|Nrf2|Nrf|data avail', 'PMC13360480':r'PMP22|Nrf2|Nrf|Data avail', 'PMC6623163':r'LXR|PMP22|promoter', 'PMC11014456':r'NRF2|Nrf2|Nqo1|Slc7a11|oxidative|antioxidant', 'PMC5658359':r'Par3[01]:|Fig\. 5c', 'PMC8168556':r'up-regulation of NRF2 transcription factor targets', 'PMC11252818':r'significantly increased SLC7A11 mRNA|mRNA levels \(Fig\. 1D'}
for pmc,pattern in patterns.items():
 p=O/(pmc+'-text.txt')
 if not p.exists():continue
 selected=[dict(source=pmc,file=str(p.relative_to(Q)),line=k,text=s) for k,s in enumerate(p.read_text().splitlines(),1) if re.search(pattern,s,re.I)]
 passages+=selected
 print('\nSOURCE',pmc)
 for a in selected:print(a['line'],a['text'][:3800])
(O/'source-novelty-passages.json').write_text(json.dumps(passages,indent=2,ensure_ascii=False))
# Exact date is from system clock, never guessed.
today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
searches=[]
for p in sorted(I.glob('novelty-*.json')):
 d=json.loads(p.read_text());searches.append(dict(query=d['request']['queryString'],date=today,evidence=str(p.relative_to(Q)),hitCount=d['hitCount'],returned=len(d.get('resultList',{}).get('result',[])),truncated=bool(d.get('nextCursorMark'))))
audit=dict(date=today,scope='Five EuropePMC exact mechanism/context searches plus primary-source inspection. Broader PMP22 query first100 of217, explicitly incomplete. No global priority claim.',searches=searches,claims=[dict(claim='Neddylation regulates Schwann EGR2 persistence and multiple myelination pathways',novelty='known',sources=['PMC11014456 Fig5-8'],difference='Repaired upstream blind spot; not new biology'),dict(claim='Neddylation inhibition can stabilize NRF2 and induce antioxidant genes',novelty='known',sources=['PMC5658359 Fig5','PMC8168556 Fig4-5','PMC11252818 Fig1'],difference='Primary evidence in non-Schwann systems; no direct transfer assumed'),dict(claim='Nae1-loss Pmp22 RNA is not relatively preserved against seven myelin genes',novelty='not_found_in_scoped_search',sources=['PMC11014456 Fig4 and Results','PMC5589416 Fig3','inherited Zeb2 analysis'],difference='New independently tested transfer rejection, not unique gene mechanism'),dict(claim='Eligible four-gene antioxidant module is stronger in Nae1 loss than in TSC1/PTEN despite shared Pmp22/myelin suppression',novelty='not_found_in_scoped_search',sources=['PMC11014456 Fig5A already compares these expression signatures','PMC5589416 Fig3 source data','PMC5658359 Fig5','PMC8168556 Fig4'],difference='New exact comparative inference; five-gene lock untestable, reduced panel retrospective; not proof of NRF2 causality'),dict(claim='Antioxidant intervention can alter peripheral myelin/PMP22 endpoints',novelty='known',sources=['PMC5802790 Fig3','PMC6944556','32980538 abstract only'],difference='Precludes claiming antioxidant-PMP22 relationship in general is new; contexts and interventions differ')],limitation='Primary abstracts only for non-PMC curcumin papers; selected full-text passages plus supplied entire JATS for closest sources. No exhaustive downstream citation/secondary-data-use audit. No novel causal regulator established.')
(O/'novelty-audit.json').write_text(json.dumps(audit,indent=2))
