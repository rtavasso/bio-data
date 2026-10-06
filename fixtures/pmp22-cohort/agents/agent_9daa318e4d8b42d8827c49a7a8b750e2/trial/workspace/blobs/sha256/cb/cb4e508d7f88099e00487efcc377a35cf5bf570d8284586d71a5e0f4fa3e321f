from pathlib import Path
from html.parser import HTMLParser
import xml.etree.ElementTree as E,re,json
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/iteration';O=Q/'outputs/iteration'
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['p','h1','h2','h3','h4','figcaption']:self.parts.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)
texts={}
for name in ['PMC5730339.html','PMC6359928.html','PMC6416471.xml','PMC10940316.xml']:
 p=D/name
 if p.suffix=='.xml':
  root=E.parse(p).getroot();t='\n'.join(' '.join(x.itertext()) for x in root.iter() if x.tag in ['p','article-title','title'])
 else:
  parser=Text();parser.feed(p.read_text());t=''.join(parser.parts)
 texts[p.stem]=t;(O/(p.stem+'-primary-text.txt')).write_text(t)
passages=[]
for paper,terms in {'PMC5730339':['PMP22','400 nM','n = 4','congruent','eIF3d'],'PMC6359928':['Translation efficiency (TE) was defined','spike-in normalization factor','independent biological replicates','only a small subset','50 in any'],'PMC6416471':['1μM or 200','GSE49598','TPM of 4','PERK WT and','repression program'],'PMC10940316':['Figure 7','dedifferentiation','Hmgcr','PTEN reduction','No evidence for molecular']}.items():
 for term in terms:
  m=re.search(re.escape(term),texts[paper],re.I)
  if m:passages.append({'source':str((D/(paper+('.html' if paper in ['PMC5730339','PMC6359928'] else '.xml'))).relative_to(Q)),'query':term,'locator':'character offset '+str(m.start())+' in outputs/iteration/'+paper+'-primary-text.txt','passage':texts[paper][max(0,m.start()-180):m.end()+1000]})
(O/'primary-passages.json').write_text(json.dumps(passages,indent=2,allow_nan=False))
audit={'date':'2026-09-28','boundary':'12 initial/mechanistic/exact-claim web search queries, plus one flag-documentation query; inspect four primary full texts and Gonen native TableS5. Not exhaustive corpus search. Original GSE49598 lacks a linked source article in series record; Gonen reused it.','search_evidence':'outputs/iteration/web-searches.json','claims':[{'claim':'Pmp22 RNA and polysome suppression during chronic ER stress','novelty_status':'known','closest_prior_work':'Guan et al2017 PMC5730339, Results Figure7 paragraph explicitly naming PMP22 as congruently regulated; Figure6 outlines RNA/polysome program','new_contribution':'New sample-level effect sizes, fraction interaction and robustness; not a newly recognized biological relationship.'},{'claim':'Uniform PERK-dependent Pmp22 repression across fibroblast experiments','novelty_status':'unresolved','closest_prior_work':'Guan2017 Figure6/7; Gonen2019 PMC6416471 TableS5A Pmp22 late cluster1 and TableS5B Pmp22 decrease','new_contribution':'Cross-study assay/context comparison plus frozen genetic test exposes nontransferability and provenance limitations. Original TableS5 already contains opposed cell-context outcomes; no claim of discovery from table values alone.'},{'claim':'Pmp22 translation loss implies granule sequestration','novelty_status':'known_general_alternative','closest_prior_work':'Namkoong et al2018 PMC6359928 Figure4 and Discussion already establish that translational suppression is not sufficient for RG recruitment','new_contribution':'Target-specific reanalysis finds replicate-dependent relative partition and missing absolute calibration. Does not establish a new Pmp22 granule mechanism.'},{'claim':'PTEN reduction restores a metabolic endpoint independently of differentiation','novelty_status':'known_negative_baseline','closest_prior_work':'PMC10940316 Figure7 already reports no differentiation rescue','new_contribution':'Hmgcr rescue not convincingly supported by native qPCR; source-count and duplicated-row anomalies limit precision. No new mechanistic uncoupling claim.'}]}
(O/'novelty-audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
