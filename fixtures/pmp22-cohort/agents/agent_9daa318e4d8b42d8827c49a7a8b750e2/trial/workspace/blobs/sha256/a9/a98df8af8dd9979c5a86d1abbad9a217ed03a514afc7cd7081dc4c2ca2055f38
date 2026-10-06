"""Known-result quantitative extraction, preserving selected-table semantics."""
from pathlib import Path
import json,hashlib,re
from defusedxml import ElementTree as ET
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit';W=Q.parents[1]
h='14e61c21916566d50f627214811adb631ebc3ceb7abc89e7a73ed4ee2fe95be3';p=W/'blobs/sha256'/h[:2]/h
assert hashlib.sha256(p.read_bytes()).hexdigest()==h;r=ET.parse(p).getroot();assert r.tag=='article'
tab=r.find('.//table-wrap');rows=[]
for i,row in enumerate(tab.findall('.//tbody/tr'),start=1):
 vals=[''.join(x.itertext()).strip() for x in row.findall('td')];assert len(vals)==6
 a,b=[float(v.replace('−','-')) for v in vals[3:5]]
 rows.append(dict(source_table='TableI',source_row=i,target=vals[0],unigene=vals[1],source_localization=vals[2],hIre1R_log2_DTT_untreated=a,Ire1KO_log2_DTT_untreated=b,source_decreased_stability=vals[5],hIre1R_fold=2**a,Ire1KO_fold=2**b,log2_stress_interaction=a-b,ratio_of_stress_fold_changes=2**(a-b)))
d=pd.DataFrame(rows);assert len(d)==26;d.to_csv(O/'ridd-source-table-effects.tsv',sep='\t',index=False)
pmp=d[d.target.str.contains('Pmp22',regex=False)].iloc[0].to_dict()
methods=next(x for x in r.findall('.//sec') if x.findtext('title')=='Microarray experiments and analysis');methods=''.join(methods.itertext());(O/'ridd-array-methods.txt').write_text(methods)
s=dict(source_blob=h,source_status='Primary articleXML verified; exact TableI values extracted. 26 selected candidates, not full microarray universe.',Pmp22=pmp,stability_categories=d.source_decreased_stability.value_counts().to_dict(),independent_units='Three independently repeated array experiments per source methods; no donor identity or per-replicate matrix available in inspected article/supplement.',design='Ire1-deficientMEFs versus same-line humanIRE1reconstitution;2mMDTT6h;each stress value relative to own untreated cells. Table averages rounded2decimals.',known_result=True,limits='No new biological discovery, error bars or replicate intervals derivable fromTableI. Selection already requiresIRE1-dependentdecrease. ECM localization retained as obsolete source annotation, not endorsed. Pmp22stabilityYes is source summary linked toS2;S2numeric timecourse not acquired. MainFigs1/3 do not displayPmp22, so nuclease-deadPmp22-specific test must not be inferred.2015Perk/structure mechanism tested otherRIDDtargets, notPmp22.')
(O/'ridd-summary.json').write_text(json.dumps(s,indent=2,allow_nan=False)+'\n');print(json.dumps(s,indent=2,allow_nan=False))
