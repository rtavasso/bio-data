"""Assemble source-backed sample units and explicitly agent-authored eligibility judgments."""
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from defusedxml import ElementTree as ET

ws=Path(os.environ['BIO_WORKSPACE'])
q=ws/'questions/q_ec00fef1019a4c6f'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def contexts(dataset):
    p=q/f'outputs/design-{dataset}.json'
    obj=json.loads(p.read_text())
    out={}
    for profile in obj['profiles']:
        for item in profile.get('facts',{}).get('related_source_context',[]):
            fields=item.get('body',{}).get('fields',{})
            if 'Sample_geo_accession' in fields:
                gsm=fields['Sample_geo_accession'][0]
                assert gsm not in out or out[gsm]==fields
                out[gsm]=fields
    return p,out

samples=[]
inputs=[]
for dataset in ['GSE137947','GSE138577','GSE177037','GSE241269']:
    p,data=contexts(dataset)
    h=sha(p)
    inputs.append({'path':str(p.relative_to(q)),'sha256':h,'role':'managed metadata export with source fields'})
    for gsm,fields in sorted(data.items()):
        ch={}
        for raw in fields.get('Sample_characteristics_ch1',[]):
            k,sep,v=raw.partition(': ')
            if sep:
                ch[k]=v
        row={'dataset':dataset,'gsm':gsm,'source_title':fields['Sample_title'][0],
             'organism':fields['Sample_organism_ch1'][0],'source_characteristics':fields.get('Sample_characteristics_ch1',[]),
             'assay':fields.get('Sample_library_strategy',[]),'source_molecule':fields.get('Sample_molecule_ch1',[]),
             'age_or_stage_source':None,'injury_day':None,'age_at_harvest_days_inferred':None,
             'compartment':None,'unit_id':None,'biological_unit':None,'individual_donor_ids':None,
             'genotype_or_perturbation':None,'pairing':None,'library_column':None,'units_and_semantics':None,
             'composition_eligible':False,'nae1_within_state_eligible':False,
             'source_locator':f'GEO:{gsm}; {dataset}; Sample_characteristics_ch1/Sample_title/Sample_data_processing',
             'metadata_export_sha256':h,'processing_verbatim':fields.get('Sample_data_processing',[]),
             'supplementary_files':[v for k,vs in fields.items() if k.startswith('Sample_supplementary_file') for v in vs],
             'annotations_authored_by':'agent_3d13b73d8248425d83c9bde26e2cece3'}
        title=row['source_title']
        if dataset=='GSE137947':
            subject=ch['subject']
            gate=title.split('_',1)[1]
            assert title==f'{subject}_{gate}' and gate in ['all','mSC','nmSC']
            row.update(age_or_stage_source='P5 (series overall_design)',compartment={'all':'all eYFP-positive Schwann gate','mSC':'high-SSC myelinating-enriched Schwann gate','nmSC':'low-SSC not-myelinating-enriched Schwann gate'}[gate],unit_id=f'{dataset}:subject:{subject}',biological_unit='one mouse; independent unit is subject, not gate',individual_donor_ids=[subject],genotype_or_perturbation='P0Cre/ReYFP/betaAct-DsRed reporter; no Nae1 perturbation',pairing='same subject across three gates',library_column=title,units_and_semantics='Native GEO featureCounts raw counts; reused supplemental matrix is gene RPKM, not counts')
        elif dataset=='GSE138577':
            stage=ch['developmental stage']
            run=ch['biological replicate']
            row.update(age_or_stage_source=stage,compartment='FACS dsRed-positive nerve cells; P1 additionally eYFP-Schwann depleted' if stage=='P1' else 'FACS dsRed-positive adult nerve cells',unit_id=f'{dataset}:{stage}:pool:{run}',biological_unit='independent biological pool, male/female source cells 1:1; donors not separately labelled',genotype_or_perturbation='P0Cre/ReYFP/betaAct-DsRed reporter; no Nae1 perturbation',pairing='clusters within same pool; not paired donors across ages',library_column=title,units_and_semantics='10x v2 UMI matrices; native captured-cell fractions deliberately selected and not tissue cell fractions')
        elif dataset=='GSE177037':
            time=ch['time point']
            day=0 if time=='Uncrushed' else int(time.split('d')[0])
            sc=ch['cell type']=='Schwann Cell from Sciatic nerve'
            row.update(age_or_stage_source=ch['age'],injury_day=day,age_at_harvest_days_inferred=18+day if day else None,compartment='O4-immunopanned Schwann cells' if sc else 'whole sciatic nerve',unit_id=f'{dataset}:pool_library:{gsm}',biological_unit='pooled 10-20 nerves' if sc else 'pooled at least 10 nerves',genotype_or_perturbation='left sciatic crush at P18; naive uncrushed comparison, no Nae1 genotype',pairing='no established matching of donors/pools across time or compartment; suffix 1/2 not a donor ID',library_column=fields['Sample_description'][0],units_and_semantics='RSEM expected counts (fractional allowed), TPM and FPKM; retained bulk/native semantics')
        elif dataset=='GSE241269':
            row.update(age_or_stage_source='P7 (series overall_design)',compartment='whole sciatic nerve RNA; epineurium removal established for immunoblots only, not assumed for RNA',unit_id=f'{dataset}:library:{title}',biological_unit='reported mouse sample; series n=4 per genotype; litter/donor block map not given',genotype_or_perturbation=ch['genotype'],pairing='unpaired genotype groups; title prefixes K/L not inferred as litter IDs',library_column=title,units_and_semantics='RSEM expected counts, TPM, FPKM; expected counts are not raw integer reads')
        samples.append(row)
counts=dict(Counter(r['dataset'] for r in samples))
assert counts=={'GSE137947':12,'GSE138577':6,'GSE177037':16,'GSE241269':8},counts
assert len({r['gsm'] for r in samples})==len(samples)
assert len({r['unit_id'] for r in samples if r['dataset']=='GSE137947'})==4
assert len([r for r in samples if r['dataset']=='GSE138577' and r['age_or_stage_source']=='P1'])==3
assert all(r['individual_donor_ids'] is None for r in samples if r['dataset']!='GSE137947')

judgment_path=q/'inputs/applicability-judgments.json'
judgments=json.loads(judgment_path.read_text())
inputs.append({'path':str(judgment_path.relative_to(q)),'sha256':sha(judgment_path),'role':'agent-authored interpretation; not measurements'})
source_evidence=[]
needles={
'snat':['negative selection','Each sample was derived from a Schwann','Each plate','Using RNA from sorted SCs'],
'nae1':['littermates MPZ-Cre','7 days old','Rat Schwann cells were isolated','RNA-seq profiling of P7','mRNA levels of','MPZ levels, however'],
'repair':['10–20 sciatic nerves','minimum of 10 nerves','postnatal day 18','dissociated sciatic nerve','room temperature','CD45-positive myeloid']}
for label,terms in needles.items():
    p=q/f'inputs/public/{label}.xml'
    h=sha(p)
    inputs.append({'path':str(p.relative_to(q)),'sha256':h,'role':'primary paper XML'})
    root=ET.parse(p).getroot()
    paragraphs=list(root.iter('p'))
    for idx,el in enumerate(paragraphs):
        text=' '.join(el.itertext())
        if any(term.lower() in text.lower() for term in terms):
            source_evidence.append({'source':label,'sha256':h,'locator':f'XML p document-order index {idx} (zero-based)','text':text})

rejects=[]
for name in ['repair-supp4.xlsx','repair-supp4-pmc.response','repair-publisher.html']:
    p=q/'inputs/public'/name
    if p.exists():
        b=p.read_bytes()
        assert not b.startswith(b'PK'), 'unexpected usable workbook: inspect before finalizing blocker'
        reason='recaptcha HTML' if b'recaptcha' in b.lower() else 'Client Challenge HTML' if b'Client Challenge' in b else 'not XLSX; unclassified'
        rejects.append({'file':name,'sha256':sha(p),'reason':reason,'not_measurement':True})
# Verify algebraic ambiguity on exact rational values, not biological measurements.
# Generic identity: w*(S+d)+(1-w)*(O-w*d/(1-w)) equals w*S+(1-w)*O.
from fractions import Fraction
w,S,O,d=Fraction(1,3),Fraction(3),Fraction(6),Fraction(1)
assert w*(S+d)+(1-w)*(O-w*d/(1-w))==w*S+(1-w)*O
assert (S+d)>0 and (O-w*d/(1-w))>0
validation={'sample_rows':len(samples),'dataset_counts':counts,'unique_gsms':len({r['gsm'] for r in samples}),'p5_subjects':4,'p1_pools':3,'eligibility_rows':len(judgments['rows']),'rejected_http200_payloads':rejects,'generic_mixture_identity_verified':True,'mixture_identity_status':'algebra check only; no synthetic biological values or fitted cell fractions','json_finite':True}
output={'sample_annotations':samples,'applicability':judgments,'primary_design_evidence':source_evidence,'input_manifest':inputs,'validation':validation,'limitations':['null donor IDs mean unresolved, not independence','source metadata typo human genome (GRCm38) retained; assembly separately says Mus musculus','rat harvest age 18+injury day inferred from paper surgery age; naive harvest not inferred from surgery','gene RNA is not promoter output; all genotype within-state eligibility flags false']}
(q/'outputs/sample-unit-audit.json').write_text(json.dumps(output,indent=2,allow_nan=False))
flat=[]
for row in samples:
    flat.append({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else '' if v is None else v) for k,v in row.items()})
for name,rows in [('sample-units.tsv',flat),('applicability.tsv',judgments['rows'])]:
    with (q/'outputs'/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
(q/'outputs/audit-validation.json').write_text(json.dumps(validation,indent=2,allow_nan=False))
print(json.dumps(validation,indent=2))
