"""Retrospective paired-gate audit; no imported code, fitting of fractions, or cell pseudoreplication."""
import csv
import gzip
import hashlib
import itertools
import json
import math
import os
import statistics
from pathlib import Path

from scipy.stats import t

ws=Path(os.environ['BIO_WORKSPACE'])
q=ws/'questions/q_ec00fef1019a4c6f'
h='1327d696aef274054f77adee2331a90dd2a0d88d7be3ba2bd119ea44598d4aba'
p=ws/'blobs/sha256'/h[:2]/h
assert hashlib.sha256(p.read_bytes()).hexdigest()==h
with gzip.open(p,'rt') as f:
    reader=csv.DictReader(f,delimiter='\t')
    rows=list(reader)
assert len({r['gene_name'] for r in rows})==len(rows)
values={r['gene_name']:{k:float(v) for k,v in r.items() if k!='gene_name'} for r in rows}
assert all(math.isfinite(v) and v>=0 for r in values.values() for v in r.values())
metadata=json.loads((q/'outputs/fields-GSE137947.json').read_text())
meta={x['fields']['Sample_title'][0]:x['fields'] for x in metadata if 'Sample_title' in x['fields']}
for subject in range(1,5):
    for gate in ['all','mSC','nmSC']:
        f=meta[f'{subject}_{gate}']
        assert f['Sample_characteristics_ch1']==[f'subject: {subject}']
antioxidants=['Nqo1','Hmox1','Gclc','Gclm']
myelin=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal']
panels={g:[g] for g in ['Pmp22']+antioxidants+myelin}
panels.update(antioxidant4=antioxidants,no_Nqo1=antioxidants[1:],myelin7=myelin)
assert all(values[g][f'{s}_{gate}']>0 for genes in panels.values() for g in genes for s in range(1,5) for gate in ['mSC','nmSC'])
results=[]
subject_rows=[]
for pc in [0.0,0.1,1.0]:
    effects={}
    for name,genes in panels.items():
        effects[name]=[statistics.mean(math.log2(values[g][f'{s}_nmSC']+pc)-math.log2(values[g][f'{s}_mSC']+pc) for g in genes) for s in range(1,5)]
    effects['Pmp22_minus_myelin7']=[a-b for a,b in zip(effects['Pmp22'],effects['myelin7'])]
    for name,diffs in effects.items():
        mean=statistics.mean(diffs)
        se=statistics.stdev(diffs)/math.sqrt(len(diffs))
        width=float(t.ppf(0.975,len(diffs)-1))*se
        null=[abs(statistics.mean(d*s for d,s in zip(diffs,signs))) for signs in itertools.product([-1,1],repeat=len(diffs))]
        exact=sum(x>=abs(mean)-1e-12 for x in null)/len(null)
        loo=[statistics.mean(diffs[:i]+diffs[i+1:]) for i in range(len(diffs))]
        results.append({'endpoint':name,'pseudocount_rpkm':pc,'n_subjects':len(diffs),'effect_log2':mean,'ci95_low':mean-width,'ci95_high':mean+width,'ci_model':'paired t, df=3; descriptive and unadjusted','signflip_p_two_sided':exact,'signflip_assumption':'symmetric independent subject differences, not randomized gates','subjects_positive':sum(d>0 for d in diffs),'subjects_negative':sum(d<0 for d in diffs),'loo_min':min(loo),'loo_max':max(loo)})
        if pc==0.1:
            for s,diff in enumerate(diffs,1):
                subject_rows.append({'subject':s,'endpoint':name,'difference_log2_nmSC_minus_mSC':diff,'nmSC_gsm':meta[f'{s}_nmSC']['Sample_geo_accession'][0],'mSC_gsm':meta[f'{s}_mSC']['Sample_geo_accession'][0]})
prior=json.loads((q/'outputs/prior-state-summary.json').read_text())
checks=[]
for name in ['Pmp22','antioxidant4','no_Nqo1','myelin7']:
    observed=next(r for r in results if r['endpoint']==name and r['pseudocount_rpkm']==0.1)
    old=next(r for r in prior['reference_primary'] if r['panel']==name and r['reference']=='sorted_nm_vs_m' and r['pseudocount']==0.1)
    delta=abs(observed['effect_log2']-old['effect'])
    assert delta<1e-10
    checks.append({'endpoint':name,'max_mean_difference_from_prior':delta})
for filename,data in [('paired-gate-results.tsv',results),('paired-subject-effects.tsv',subject_rows)]:
    with (q/'outputs'/filename).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]),delimiter='\t')
        writer.writeheader()
        writer.writerows(data)
summary={'source_matrix_sha256':h,'feature_rows':len(rows),'units':'source RPKM, mature gene RNA; no absolute molecules/cell','contrast':'P5 nmSC-enriched minus mSC-enriched gates within 4 GEO subjects','analysis_status':'retrospective reanalysis of previously exposed source, not independent replication','prerequisites':['all target entries finite and strictly positive','unique source gene labels','all 12 titles explicitly linked to subjects 1-4'],'agreement_checks':checks,'primary':[r for r in results if r['pseudocount_rpkm']==0.1],'limitations':['gates enriched not pure states; no genotype contrast','4 animals not 12 independent gates or cells','paired t intervals descriptive, no multiplicity correction','exact sign-flip resolution limits inference with four subjects','cannot transport baseline P5 association to Nae1 pathological P7','RNA normalization not absolute cell output']}
(q/'outputs/paired-audit-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
print(json.dumps(summary,indent=2,allow_nan=False))
