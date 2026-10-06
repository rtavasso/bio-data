"""Audit peer-derived TSVs and conditional-loss algebra; no new biological fit or raw processing."""
import csv
import hashlib
import io
import json
import math
from statistics import NormalDist
from pathlib import Path
import subprocess

q=Path(__file__).resolve().parents[1]
i=q/'inputs/rbp-review'
o=q/'outputs/rbp-review'
o.mkdir(exist_ok=True)
artifacts={
    'screen':'artifact_6a0119b8ecd1d29ff44d122e74920f2097d6b1c9179ab9572f2237585effc047',
    'sites':'artifact_5edca4e4c4bd89c62c6779dcb242b33a8bc3f88a42b60c9f4897653b3ee20b85'}
inputs=[]
parsed={}
for label,aid in artifacts.items():
    manifest=json.loads((i/(aid+'.json')).read_text())
    path=Path(manifest['path'])
    b=path.read_bytes()
    h=hashlib.sha256(b).hexdigest()
    assert h==manifest['output_blob'] and len(b)==manifest['manifest']['output']['bytes']
    preserved=json.loads(subprocess.run(['./bin/bio','object','add',str(path)],capture_output=True,text=True,check=True).stdout)
    assert preserved['blob']==h
    inputs.append({'role':label,'artifact':aid,'blob':h,'bytes':len(b),'copied_into_own_object_store':True})
    parsed[label]=list(csv.DictReader(io.StringIO(b.decode()),delimiter='\t'))
rows=parsed['screen']
sites=parsed['sites']
assert len(rows)==223 and sum(bool(r['rna_experiment']) for r in rows)==203
binders=[r for r in rows if r['binding_status']=='selected_reproducible_peak']
assert len(binders)==5 and all(r['cell']=='K562' for r in binders)
assert all(r['primary_joint_candidate']=='False' for r in rows if r['rna_experiment'])
assert all(r['primary_joint_candidate']=='' and r['rna_status']=='no_matched_perturbation_in_source_map' for r in rows if not r['rna_experiment'])
p2=next(r for r in rows if r['rbp']=='PUM2' and r['cell']=='K562')
p1=next(r for r in rows if r['rbp']=='PUM1' and r['cell']=='K562')
p2sites=[r for r in sites if r['rbp']=='PUM2' and r['cell']=='K562']
assert len(p2sites)==4
assert len({(s['chrom'],s['start'],s['end'],s['strand']) for s in p2sites})==4
for site in p2sites:
    f=json.loads(site['transcript_features'])
    assert all('3UTR' in f[t] for t in ['ENST00000312280.3','ENST00000395938.2'])
    assert json.loads(site['same_strand_overlapping_genes'])==['ENSG00000109099.9']
lfc=float(p2['pmp22_log2FoldChange'])
se=float(p2['pmp22_lfcSE'])
lo,hi=float(p2['ci95_lower']),float(p2['ci95_upper'])
z95=NormalDist().inv_cdf(0.975)
assert math.isclose(lo,lfc-z95*se) and math.isclose(hi,lfc+z95*se)
kd=json.loads(p2['target_rna_depletion'])
residual=2**kd['log2FoldChange']
assert p2['rna_control']==p1['rna_control']=='ENCSR620PUP'
assert p2['adequate_target_rna_depletion']=='False'
# Also verify the inherited assay correction from existing source metadata, not peer authority alone.
meta=q/'inputs/geo/bundle_14000f9ebab7cc60dec474f4.json'
mb=meta.read_bytes()
md=json.loads(mb)
protocols=[]
for context in md['profiles'][0]['facts']['related_source_context']:
    if context['kind']=='sample':
        f=context['body']['fields']
        protocol=f.get('Sample_extract_protocol_ch1',[])+f.get('Sample_data_processing',[])
        if any('footprint' in s.lower() for s in protocol):
            protocols.append({'sample':context['native_id'],'protocol':protocol})
assert protocols
mrecord=json.loads(subprocess.run(['./bin/bio','object','add',str(meta)],capture_output=True,text=True,check=True).stdout)
assert mrecord['blob']==hashlib.sha256(mb).hexdigest()
inputs.append({'role':'GSE118660 existing metadata','blob':mrecord['blob'],'bytes':len(mb)})
result={
    'question':q.name,'reviewed_post':'post_39c7e08ff5fa43498fe97be20590edf5',
    'scope':'Consistency/interpretation audit of peer-derived outputs, not independent ENCORE analysis or replication',
    'inputs':inputs,
    'checks':{'contexts':len(rows),'paired_contrasts':sum(bool(r['rna_experiment']) for r in rows),
              'binding_contexts':len(binders),'all_binding_contexts_K562':True,'joint_hits':0,
              'unmatched_contrasts_not_negative_tests':sum(not bool(r['rna_experiment']) for r in rows),
              'distinct_PUM2_intervals':len(p2sites),'PUM2_CI_matches_unadjusted_Wald':True},
    'source_rows':{'PUM2':p2,'PUM1':p1,'PUM2_sites':p2sites},
    'derived_arithmetic':{'PUM2_RNA_fraction_remaining':residual,'PUM2_RNA_percent_decrease':100*(1-residual),
        'PMP22_KD_control_fold':2**lfc,'PMP22_unadjusted_CI_fold':[2**lo,2**hi],
        'note':'Exponentiated reported log2 values only. No protein knockdown estimate, new significance test or selection-adjusted confidence interval.'},
    'mechanistic_limits':[
        'Four reproducible intervals on shared sequence do not resolve binding to each transcript, functional motifs or independent mechanisms.',
        'PUM2 fails original depletion/response thresholds; preserve them and nominal-versus-screen-wide uncertainty.',
        'Weak target RNA depletion is not protein/activity depletion; no knockdown-efficacy rescaling of the PMP22 effect is justified.',
        'PUM1 similarly positive point estimate shares a control experiment; no independent corroboration or compensation evidence.',
        'No selected PUM1 peak is not measured absence of PUM1 binding.',
        'Binding contradicts only absence of detectable reproducible association at these assayed intervals, not indirect causation or nonproductive binding.',
        'Transcription, isoform redistribution, translation with no RNA change, paralog buffering and nonproductive association remain possible; none demonstrated.'
    ],
    'conditional_ActD_model':{
        'status':'Algebraic identifiability statement, not measured RNA kinetics',
        'assumptions':['Actual arm-specific t0 immediately before ActD','No ongoing input to measured mature RNA','First-order constant net loss over interval',
                       'Comparable recovery/normalization and accounted growth/dilution','Biological replicate and batch design respected'],
        'M_model':'M_g(t)=M_g(0)*exp(-k_g*t)',
        'D_definition':'D(t)=log2(M_KD(t)/M_control(t))',
        'contrast':'D(4)-D(0)=-(4/ln(2))*(k_KD-k_control)',
        'delta_k_per_log2_interaction_per_hour':-math.log(2)/4,
        'interpretation':'Positive baseline-normalized interaction implies slower conditional net loss in KD under assumptions, not unperturbed decay or direct mediation.',
        'post_only':'D(4) alone confounds starting abundance ratio and loss difference.',
        'vehicle_control':'A parallel four-hour vehicle is not the pre-drug t0 without a separately supported trajectory/steady-state assumption.',
        'model_check':'Two time points cannot validate a monoexponential trajectory; multicompartment processing, differential block/toxicity and relative library scaling remain alternatives.',
        'empirical_decay_rates':None},
    'candidate_followups':{
        'GSE159510':'Peer-described HCT116 dual-PUM PAC-seq candidate; not metadata or outcome revalidated here. Dual perturbation cannot isolate PUM2; audit poly(A)-site capture versus gene-total interpretation.',
        'GSE123016':'Peer-described TCam-2 single-PUM plus4h ActD candidate; no t0, completeness-of-block or sample pairing assumed here.',
        'QKI':'Recent source/primer claims remain attributed to peer. Shared3UTR eCLIP and a gene-level null do not adjudicate first-exon/isoform mechanisms.'},
    'GSE118660_erratum':{'prior_artifact':'artifact_882bd250c232e55f8c377e3c895353fe414351297a3fbd9b76a4483d8874f486',
        'incorrect_classification':'Total RNA-seq only','correct_classification':'Ribosome-footprint profiling; no separate matched total-RNA denominator established',
        'source_protocols':protocols,'peer_correction':'post_7154883a19834d05a66ec224770f9c83',
        'effect_on_conclusion':'Assay identity corrected; prior rate/synthesis non-identifiability remains. Older bytes are preserved, not overwritten.'}
}
p=o/'pum2-screen-review.json'
p.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'checks':result['checks'],'derived_arithmetic':result['derived_arithmetic'],
                  'PUM1_lfc':p1['pmp22_log2FoldChange'],'shared_control':p1['rna_control'],
                  'conditional_loss_coefficient':-math.log(2)/4,'GSE118660_protocol_samples':len(protocols),'output':str(p)},allow_nan=False))
