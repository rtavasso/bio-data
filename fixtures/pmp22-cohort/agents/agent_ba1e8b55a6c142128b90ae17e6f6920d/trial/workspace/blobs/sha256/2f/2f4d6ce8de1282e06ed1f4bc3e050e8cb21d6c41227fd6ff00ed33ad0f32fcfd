"""Descriptive arithmetic on explicit published measurement summaries, not raw replicates."""
from pathlib import Path
from html.parser import HTMLParser
import re,json,hashlib,csv
q=Path(__file__).resolve().parents[1];p=q/'inputs/continuation/PMC6607759.html';o=q/'outputs'
class P(HTMLParser):
 def __init__(self):super().__init__();self.inside=False;self.buf=[];self.paras=[]
 def handle_starttag(self,t,a):
  if t=='p':self.inside=True;self.buf=[]
 def handle_endtag(self,t):
  if t=='p' and self.inside:self.paras.append(''.join(self.buf));self.inside=False
 def handle_data(self,s):
  if self.inside:self.buf.append(s)
s=P();s.feed(p.read_text());protein=next(t for t in s.paras if '1.53-fold' in t and '81.9' in t);efflux=next(t for t in s.paras if '17.4' in t and '3.8' in t)
fold=re.search(r'([\d.]+)-fold higher.*?([\d.]+)-fold increase',protein);assert fold
frac=re.search(r'WT ([\d.]+) ± ([\d.]+)% vs ABCA1 HET ([\d.]+) ± ([\d.]+)% vs ABCA1 KO ([\d.]+) ± ([\d.]+)%',protein);assert frac
v=list(map(float,frac.groups()));total=[1.,float(fold[2]),float(fold[1])];rows=[]
for i,g in enumerate(['WT','ABCA1_HET','ABCA1_KO']):
 fraction=v[2*i]/100
 rows.append({'genotype':g,'published_total_PMP22_fold':total[i],'published_endoH_resistant_percent':v[2*i],'published_SEM_percent':v[2*i+1],'summary_product_resistant_index_relative_WT':total[i]*fraction/(v[0]/100),'summary_product_sensitive_index_relative_WT':total[i]*(1-fraction)/(1-v[0]/100)})
with (o/'lipid-protein-summary-derived.tsv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
summary={'source':str(p.relative_to(q)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_endpoint':'10-month-old mouse sciatic nerve total PMP22 Western blot and endoH sensitivity; Figure4D-G, 4-5 mice/genotype source-reported','exact_primary_paragraphs':[protein,efflux],'rows':rows,'interpretation':'Total PMP22 increase coexists with lower endoH-resistant fraction. Multiplying source group summaries yields a resistant-pool index near WT, motivating distinction between total and processed protein. This is NOT a directly measured paired mature abundance, surface abundance, myelin localization, or a statistical null result.','assumption':'Product of means is an illustrative reconstruction; absent per-sample pairing/covariance prevents an uncertainty interval or formal genotype test for this derived index. No claim that endoH resistance equals functional myelin protein.','feedback_boundary':'Reciprocal ABCA1-to-PMP22 total/processing effect supported; mechanism of a direct cholesterol-to-PMP22 transcriptional feedback remains unmeasured.'}
(o/'lipid-summary-analysis.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(rows,indent=2))
