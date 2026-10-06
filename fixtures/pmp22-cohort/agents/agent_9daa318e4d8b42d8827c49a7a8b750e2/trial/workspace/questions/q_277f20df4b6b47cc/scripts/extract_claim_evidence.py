"""Preserve exact primary paragraphs for endpoint/design audit; not replicate data."""
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET
import json,re,hashlib,csv
q=Path(__file__).resolve().parents[1]; d=q/'inputs/continuation';o=q/'outputs'
class Paragraphs(HTMLParser):
 def __init__(self):super().__init__();self.level=0;self.parts=[];self.rows=[]
 def handle_starttag(self,t,a):
  if t=='p':self.level+=1;self.parts=[]
 def handle_endtag(self,t):
  if t=='p' and self.level:self.rows.append(''.join(self.parts));self.level-=1
 def handle_data(self,s):
  if self.level:self.parts.append(s)
spec={
 'PMC5800313.html':r'nuclear run-on|38-fold|steady-state levels of gene expression|Ser184|Type III|Methods for Sciatic',
 'PMC11592338.xml':r'featureCounts|HISAT|48 h|WDR5|H3K4me3|H3K27me3',
 'PMC2713384.html':r'primed|microRNAome|ten crush|at least two|0\.78|0\.078|seed region|Dicer.*inhibit',
 'PMC5181599.html':r'technical|P20|hg18|rescue',
 'PMC7322568.html':r'P1|CRISPR|deletion|deletions',
 'PMC8191293.xml':r'LMAN1|UGGT1|six biological|batch-to-batch',
 'PMC6482019.xml':r'ATAC-seq|replicate|stop codon',
 'PMC6920087.xml':r'48 h|72 h|fibroblast|patient',
}
rows=[]
for file,pattern in spec.items():
 p=d/file
 if p.suffix=='.html':parser=Paragraphs();parser.feed(p.read_text());paras=parser.rows
 else:paras=[''.join(e.itertext()) for e in ET.parse(p).getroot().iter('p')]
 for n,t in enumerate(paras,1):
  if re.search(pattern,t,re.I):rows.append({'source':str(p.relative_to(q)),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'paragraph_index':n,'exact_text':t})
(o/'audited-source-passages.json').write_text(json.dumps({'purpose':'Exact primary-source text for review; selected paragraphs, not a full data matrix or new numerical biological analysis','paragraphs':rows},indent=2))
audit=[
 ['2017 Egr2-AS','mouse myelinated DRG','lentiviral AS versus control','Egr2 RNA and protein lower','Figure 2','different material/time from rat48h RNAseq'],
 ['2017 Egr2-AS','Schwann cells; supplemental exact timing not recovered','AS versus control','nascent Egr2 lower by nuclear run-on','Figure 5A','8/9 observations derive from three experiments; not 8/9 donors'],
 ['2017 Egr2-AS','injured mouse sciatic nerve','AS GapMer versus scrambled','Egr2 RNA about38x at6h; equal24h; about3x48h','Figure 5F and Results','published summaries; no new effect estimate or p-value'],
 ['2024 Egr2-AS','primary rat Schwann cells','48h AS versus GFP','Egr2 RNA1.258x; Jun0.820x; Pmp22.885x','GSE201623; RNA audit','new full-count analysis; library independence unresolved'],
 ['2024 Egr2-AS','primary rat Schwann cells','AS versus control','EGR2 protein down; C-JUN protein/activity up','supplement Figures S1A/S2D','source bars visually inspected; not digitized; no same-culture endpoint mapping'],
 ['2009 miR29','newborn rat Schwann cultures','miR29a/anti-miR29a and seed deletion','endogenous RNA/protein and reporter effects','Figures5-7','engineered AGO2/miR29 RIP supports association; not endogenous loading across injury'],
 ['2009 miR29','developing rat nerve / mouse nerve crush','development / injury','miR29 inversely associated with PMP22','Figures8-9 and Methods','at least2 rats pooled per developmental sample;10 mouse nerves pooled; triplicates not10 independent measurements; r2 .78 Results versus .078 caption unresolved'],
 ['RUNX/NF1','mouse DRG sKO versus tumor tKO annotations','Nf1 versus Nf1/Runx1/Runx3 knockout','quantitative normalized ATAC tracks','GSE122776','one library/genotype; context-confounded; descriptive signal only'],
 ['PMP22 glycosylation','tagged human protein in HEK293','WT/N41Q/L16P co-IP versus mock','selected TMT enrichment over mock','TableS1/PXD023091','not total protein abundance; six biological co-IPs per construct source-reported; no replicate matrix'],
 ['human dosage','7 cultured Schwann donors/12 arrays','BAR duplication and JIM L16P separately versus3 normals','log10 two-color expression ratio','GSE7423/GPL1708','one donor per mutation; technical duplicates; no dosage coefficient or P1/P2 attribution'],
]
with (o/'assay-endpoint-audit.tsv').open('w') as f:
 w=csv.writer(f,delimiter='\t');w.writerow(['study','material','contrast','endpoint','locator','limitation']);w.writerows(audit)
print('Preserved',len(rows),'exact source paragraphs;',len(audit),'endpoint-audit rows')
