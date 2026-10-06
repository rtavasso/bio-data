"""Preserve primary-text locators and dated query boundaries; no novelty inference from co-mention alone."""
from pathlib import Path
from html.parser import HTMLParser
from xml.etree import ElementTree as E
import json,re
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/specific';O=Q/'outputs/specific'
class Parser(HTMLParser):
 def __init__(self):super().__init__();self.text=[]
 def handle_data(self,d):self.text.append(d)
texts={};sources={'PMC9063194':'PMC9063194.xml','PMC4964942':'PMC4964942.xml','PMC4961522':'PMC4961522.html','PMC2440619':'PMC2440619.html','PMC6289291':'PMC6289291.html','Cufflinks':'cufflinks-file-formats.html'}
for key,name in sources.items():
 p=D/name
 if p.suffix=='.xml':
  root=E.parse(p);parts=[' '.join(e.itertext()) for e in root.findall('.//p')];texts[key]=parts
 else:
  z=Parser();z.feed(p.read_text());text=' '.join(z.text);text=re.sub(r'\s+',' ',text);texts[key]=[text]
passages=[]
terms={'PMC9063194':['myelin','purif','module','Sparcl1','Sema5a'],'PMC4964942':['myelin-associated','Pmp22','Sox2','microarray','Dhh','log2'],'PMC4961522':['Pmp22','P0-Cre','Dhh','Cnp','Hey2','RNA-Sequencing'],'PMC2440619':['Hck','NAB','Pmp22'],'PMC6289291':['Pmp22','contralateral','RNA-seq'],'Cufflinks':['HIDATA','FPKM_status','too many fragments']}
for key,parts in texts.items():
 for i,text in enumerate(parts):
  for term in terms[key]:
   start=0
   for n in range(8):
    j=text.lower().find(term.lower(),start)
    if j<0:break
    excerpt=text[max(0,j-250):min(len(text),j+900)];passages.append({'source':'inputs/specific/'+sources[key],'source_id':key,'locator':f'paragraph_index {i}; normalized_text_offset {j}; term {term}','term':term,'passage':excerpt});start=j+len(term)
(O/'primary-literature-passages.json').write_text(json.dumps(passages,indent=2,ensure_ascii=False))
queries=[]
for p in sorted(D.glob('novelty-*.json')):
 d=json.loads(p.read_text());result=d.get('resultList',{}).get('result',[]);queries.append({'receipt':str(p.relative_to(Q)),'query':d.get('request',{}).get('queryString',d.get('request',{})),'hitCount':d.get('hitCount'),'returned':len(result),'date':'2026-09-27','titles':[{'title':r.get('title'),'pmcid':r.get('pmcid'),'id':r.get('id')} for r in result]})
# Read all returned abstract text where supplied; save relevant local snippets without claiming unavailable full texts inspected.
abstracts=[]
for p in D.glob('novelty-*.json'):
 for r in json.loads(p.read_text()).get('resultList',{}).get('result',[]):
  abstract=r.get('abstractText','')
  if abstract:abstracts.append({'receipt':str(p.relative_to(Q)),'title':r.get('title'),'pmcid':r.get('pmcid'),'abstract':abstract})
(O/'novelty-abstracts.json').write_text(json.dumps(abstracts,indent=2,ensure_ascii=False));(O/'novelty-search-audit.json').write_text(json.dumps(queries,indent=2,ensure_ascii=False))
# Explicit evidence/novelty distinction, with close prior work and exact relationship.
audit={'date':'2026-09-27','baseline':[{'source':'PMC9063194','locator':'Results Fig2D; WGCNA analysis','known':'Purified Schwann injury transcriptome already reports myelin loss, state modules, AGE/RAGE, Sparcl1 and Sema5a. Our residual screen is a new computation, not a new injury program.'},{'source':'PMC4964942','locator':'Results; Fig3/4; Discussion','known':'Zeb2 loss blocks differentiation; persistent Sox2/Ednrb/Hey2 and myelin-gene reduction were already reported.'},{'source':'PMC4961522','locator':'Abstract; Results Notch-Hey2; RNA-seq Methods','known':'Zeb2 recruits HDAC/NuRD and suppresses inhibitory signaling; this is established, not discovered here.'},{'source':'PMC2440619','locator':'Table1; Results Activation of Egr2 target genes in Egr2-null mice','known':'Hck induction after dominant-negative NAB2 and Egr2 deficiency was reported. This is a shared-upstream alternative to Hck causing Pmp22 repression; no direct Hck-to-Pmp22 effect established by that paper.'}], 'candidate_novelty':{'Ppp6r1':{'status':'unresolved','finding':'No direct Schwann-cell Ppp6r1-to-Pmp22 specificity study identified in scoped exact-name and nerve searches. Two exact PMP22 co-mentions are unrelated topics. Incomplete full-text/synonym coverage and failed validation prohibit novel-mechanism claim.'},'Gtf2f1':{'status':'unresolved','finding':'Exact names/TFIIF/RAP74 plus PMP22 yielded13 records, mostly broad neuropathy or omics co-mentions; no direct target-specific mechanism established in inspected primary papers. Full corpus not exhaustively audited.'},'Hck':{'status':'unresolved','finding':'Hck participation in the Egr2/NAB myelination program is known. The specific Hck-to-Pmp22 residual predictor claim is not established, and validation failed. Do not call the gene a novel Schwann regulator.'}},'search_boundary':'EuropePMC indexed full-text/metadata queries with source/synonyms and separate title/abstract query; dated cutoff where explicit. Search hits can be supplemental-list membership. Primary full texts inspected for discovery, both Zeb2 studies, Eed and Egr2/NAB. No exhaustive all-language or citation-chain priority claim. Early broad queries lacked a date cutoff; dated narrower queries supersede them for novelty scope.','conclusion':'No novel mechanism claimed; new exploratory associations failed frozen primary prediction. Known shared-upstream regulation and broad residual target prediction remain better-supported alternatives.'}
(O/'literature-novelty-audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False));print('saved',len(passages),'passages;',len(queries),'queries;',len(abstracts),'abstract records')
