"""Generate endpoint table, robustness grid, uncertainty map and final synthesis from verified results."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
P=ROOT/'inputs/public'

def load(name):
    return json.loads((OUT/name).read_text())

def write_json(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,allow_nan=False))

def fmt(x):
    return f'{x:.3f}'

j=load('jci-contrasts.json')
u=load('uggt-maturation.json')
h=load('hrp-summary.json')
v=load('independent-checks.json')
assert v['valid']
notes=json.loads((ROOT/'inputs/interpretation-notes.json').read_text())
spec=json.loads((ROOT/'inputs/analysis-specification.json').read_text())
with (OUT/'hrp-gene-contrasts.tsv').open() as f:
    genes={r['gene']:r for r in csv.DictReader(f,delimiter='\t')}
wb=openpyxl.load_workbook(P/'CAM40408-S4.xlsx',read_only=True,data_only=False,keep_links=False)
raw=list(wb.worksheets[0].values)[1:]
wb.close()
# Full Cartesian background/control sensitivities, no imputation or hidden controls.
contexts=defaultdict(list)
for r in raw:
    contexts[(r[0],r[5])].append(r)
full=defaultdict(list)
for (plate,repeat),rows in contexts.items():
    bg=np.array([r[3:5] for r in rows if r[2]=='No_cell_control'])
    nt=np.array([r[3:5] for r in rows if r[2].startswith('ON-TARGETplus')])
    for background_name,background in [('mean',bg.mean(0)),('median',np.median(bg,0))]:
        for control_name,control in [('mean_NT',nt.mean(0)),('NT1',nt[0]),('NT2',nt[1])]:
            for r in rows:
                if 'ontrol' in r[2]:
                    continue
                values=np.array(r[3:5])-background
                denom=control-background
                valid=bool((values>0).all() and (denom>0).all())
                cl,sn=values/denom
                full[r[2]].append({'plate':plate,'repeat':repeat,'background':background_name,'control':control_name,'valid':valid,'SN':float(sn),'CL':float(cl),'SN_CL':float(sn/cl) if cl!=0 else None})
grid=[]
for cutoff in [1.10,1.25,1.50]:
    main=[]
    robust=[]
    for gene,values in full.items():
        baseline=[r for r in values if r['background']=='mean' and r['control']=='mean_NT']
        if all(r['valid'] and r['SN']>=cutoff and r['SN_CL']>=cutoff for r in baseline):
            main.append(gene)
        if all(r['valid'] and r['SN']>=cutoff and r['SN_CL']>=cutoff for r in values):
            robust.append(gene)
    grid.append({'cutoff':cutoff,'main_n':len(main),'full_NT_background_n':len(robust),'main_genes':sorted(main),'full_NT_background_genes':sorted(robust)})
robustness={'threshold_grid':grid,'selected_full_grid':{g:full[g] for g in ['ACSL5','ERVFRD-1','FCF1','PEX2','GPR161','TMEM220']},'ACSL5_minimum_SN_across_grid':min(r['SN'] for r in full['ACSL5']),'ACSL5_minimum_SN_CL_across_grid':min(r['SN_CL'] for r in full['ACSL5']),'ACSL5_untreated_comparator':v['sensitivity']['ACSL5']['untreated_comparator'],'unknown_covariance_sensitivity':v['cargo_interaction_covariance_sensitivity']}
write_json('robustness-grid.json',robustness)
# Each row has one endpoint; no surface reconstructed from total x mean fraction.
table=[]
def add(control,treatment,cargo,context,endpoint,estimate,uncertainty,unit,grade,limit,locator):
    table.append({'control':control,'perturbation':treatment,'cargo':cargo,'context':context,'endpoint':endpoint,'estimate':estimate,'uncertainty_or_repeat_values':uncertainty,'unit':unit,'evidence_grade':grade,'applicability_limit':limit,'source_locator':locator})
for cargo,results in j['counter_screen'].items():
    for endpoint,r in results.items():
        add('DMSO (caption 0.1%, workbook 0.2%)','VU0494372 10uM 16h',cargo,'Transient HEK293; no PMP22 disease-genotype comparison',endpoint,fmt(r['geometric_fold'])+' geometric fold',','.join(map(fmt,r['fold_95ci']))+' unpaired 95% model interval','3 reported biological replicates per arm','selection-conditioned descriptive contrast','Unknown row/cargo pairing, tag details and fluorescence artefacts; no function', 'JCI201297-data-native.xlsx / Sup. Fig. 4'+('B' if cargo=='PMP22' else 'A'))
for r in j['five_compounds']:
    add('DMSO',r['compound']+' 10uM 16h','KCNQ1 WT','Stable inducible LLP-int HEK293T',r['endpoint'],fmt(r['geometric_fold'])+' geometric fold',','.join(map(fmt,r['fold_95ci']))+' exploratory unadjusted model interval',f"{r['n_control']} control / {r['n_treated']} treated cultures",'selected follow-up','Shared control group, no multiple-testing confirmation; not PMP22','JCI201297-data-native.xlsx / Sup. Fig. 3A-C')
for r in j['kcnq1_variants']:
    add('DMSO 0.2%','VU0494372 20uM 16h','KCNQ1 '+r['variant'],'Stable population LLP-int cells, no KCNE1',r['endpoint'],fmt(r['geometric_fold'])+' geometric fold',','.join(map(fmt,r['fold_95ci']))+' model interval','4 reported biological replicates/arm','selected cargo/variant association','KCNQ1 mutants are not PMP22 mutants; function assayed in different CHO context','JCI201297-data-native.xlsx / Fig. 3A-C')
for gene in ['ACSL5','ERVFRD-1','FCF1','PEX2','GPR161','TMEM220','FAM98B','FAM102B','MXRA7']:
    g=genes[gene]
    for endpoint,key in [('secreted_HRP_activity','SN_fold'),('intracellular_HRP_activity','CL_fold'),('SN_to_CL_activity_ratio','SN_CL_fold')]:
        a,b=float(g[key+'_repeat1']),float(g[key+'_repeat2'])
        add('Plate/repeat NT after no-cell background',gene+' siRNA','ssHRP','HeLa 72h; selected follow-up screen',endpoint,fmt(a)+' / '+fmt(b)+' fold','Two independent repeats; all comparator sensitivities supplied','Culture well, 2 repeats','screening submechanism candidate' if g['gain_rule']=='True' else 'endpoint-specific caution/retention contrast','No PMP22; luminescence activity not mass or viable-cell-normalized flux; no per-target addback','CAM40408-S4.xlsx / '+g['gene'])
for r in u['contrasts_2h']:
    add(r['control'],r['treatment'],'Endogenous IGF1R','HEK293-EBNA1-6E; 1h radioactive pulse, 2h chase','surviving_labeled_mature_fraction',fmt(r['effect'])+' percentage points',','.join(map(fmt,r['unpaired_model_95ci']))+' model interval','3 biological experiment series','orthogonal lectin-cycle support','Fraction among surviving labeled cargo; not initial-cohort yield, surface or PMP22','elife-63997-fig5-data1.xlsx / L56:AI58')
for r in u['steady_state']:
    c=r['fraction_contrast']
    add('No DNJ','DNJ',r['cargo'],'HEK293-EBNA1-6E; steady-state immunoblot','mature_band_fraction',fmt(c['effect'])+' percentage points',','.join(map(fmt,c['unpaired_model_95ci']))+' model interval','4 native biological replicate labels','within-lane maturation contrast','Uncalibrated band totals not protein amount; text/caption exposure duration differs','elife-63997-fig5-data1.xlsx / N19:Q37')
with (OUT/'candidate-contrast-table.tsv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(table[0]),delimiter='\t')
    writer.writeheader()
    writer.writerows(table)
write_json('candidate-contrast-table.json',table)
# Source/query/access manifest separates successful acquisition from semantic failure.
locators=[]
for path in sorted(P.glob('*.receipt.json')):
    r=json.loads(path.read_text())
    body=P/path.name.removesuffix('.receipt.json')
    if r.get('complete_body'):
        assert body.is_file() and hashlib.sha256(body.read_bytes()).hexdigest()==r['sha256']
    locators.append({'receipt':str(path.relative_to(ROOT)),'body':str(body.relative_to(ROOT)),'url':r['url'],'status':r.get('status'),'error':r.get('error'),'sha256':r.get('sha256'),'content_type':r.get('headers',{}).get('content-type'),'note':'HTTP 200 is not sufficient for usable native data; consult access-eligibility notes.'})
write_json('source-locators.json',{'transports':locators,'access_eligibility':notes['independent_validation'],'actual_execution':'Only saved direct HTTP receipts and local CLI evidence are claimed. Earlier unsupported discovery-tool wording is withdrawn in LABBOOK.'})
queries=[]
for name in ['novelty-specific-cargos','novelty-specific-pmp','novelty-pmp-candidates','validation-general-screen','candidate-secretion','candidate-acsl5-er']:
    d=json.loads((P/(name+'.json')).read_text())
    returned=len(d.get('resultList',{}).get('result',[]))
    queries.append({'name':name,'hit_count':d['hitCount'],'returned':returned,'complete_returned_set':d['hitCount']==returned,'receipt':name+'.json.receipt.json'})
write_json('novelty-validation-audit.json',{'primary_claims':notes['primary_claims'],'queries':queries,'validation':notes['independent_validation'],'conclusion':'No verified novel PMP22 mechanism. Previously published assays support a new endpoint/replicate sensitivity analysis and an ACSL5 cargo hypothesis; targeted absence of abstracts is not proof of novelty.'})
branches=[
    {'question':'Does another membrane-cargo corrector improve measured PMP22 surface signal?','test':'JCI S4B compared with S4A','status':'No improvement demonstrated, not equivalence','next':'Independent preregistered matched cargo assay with verified construct/vehicle and viable-cell normalization'},
    {'question':'Can a general cargo handling regulator increase delivered amount rather than shrink the denominator?','test':'366 HRP siRNA labels, two repeats, full NT/background grid','status':'ACSL5 gain in reporter activity with near-unchanged intracellular activity; FCF1/ERVFRD-1 also pass; threshold/comparator dependent','next':'Frozen other-protein prediction remains unevaluated; mass/viability assay and independent reagents discriminate'},
    {'question':'Do generic secretion hits distinguish retained accumulation from loss of reporter?','test':'TMEM220 versus GPR161/FAM98B repeat-specific CL and SN','status':'TMEM220 retention-like; GPR161 and FAM98B ratio direction reverses','next':'Compare mature/ER pools and viable-cell amounts without averaging away repeat conflict'},
    {'question':'Is less glycan surveillance intrinsically productive?','test':'IGF1R UGGT1/2/ALG6 pulse-chase and DNJ IGF1R/HEXB','status':'Maturation loss, especially ALG6; not improved delivery','next':'PMP22-specific initial-cohort yield needed; no transfer from annotation-only Q01453'},
    {'question':'Does increased membrane localization assure function?','test':'KCNQ1 coding variants and separate CHO-KCNE1 currents','status':'Not uniformly; cell-level counts/nesting and context differ','next':'Do not label PMP22 myelin rescue without a functional endpoint'}]
write_json('uncertainty-map.json',{'branches':branches,'prediction':json.loads((ROOT/'inputs/frozen-acsl5-validation-prediction.json').read_text()),'decision':notes['decision']})
# Human-readable report, all displayed numerical results drawn from generated outputs.
a=genes['ACSL5']
pmp=j['counter_screen']['PMP22']['surface']
k=j['counter_screen']['KCNQ1']['surface']
interaction=j['cross_cargo']['surface']
lines=[
'# Productive trafficking: quantitative findings and limits',
'',
'Question q_9598a00912a748ce; agent_658d8df4f8694638ae0a1b33cb42ab44. This is a new round-two question, not a continuation claiming ownership of inherited execution.',
'',
'## Strongest finding',
'',
f"In the full selected HRP follow-up universe ({len(genes)} siRNA target labels), ACSL5 loss increases supernatant HRP activity by {fmt(float(a['SN_fold_repeat1']))}/{fmt(float(a['SN_fold_repeat2']))}-fold in two independent repeats while intracellular activity is {fmt(float(a['CL_fold_repeat1']))}/{fmt(float(a['CL_fold_repeat2']))}-fold. Thus this lead is not created merely by a falling intracellular denominator. It is an assay-specific candidate for cargo handling, not a demonstrated PMP22 improver.",
'',
'Competing explanations remain: enhanced export of enzyme mass, altered folding/enzymatic activity, altered cell number/viability, or a gene-pool off-target effect. None is resolved by the HRP activity assay alone. There is no evidence here to recommend systemic ACSL5 inhibition.',
'',
'## Coverage, units and prior reuse',
'',
'Parent assay-eligibility artifact_25c1966e32450880c6bd477437f61e7b6119ec298ac6b01aa81b6eff30a6b24e was fetched, its derivation inspected and linked as used. It prevented reconstructing RER1 absolute surface levels from marginal summaries, equating binding with necessity, and treating PXD043917 identifications as abundance. No inherited scientific code was executed.',
'',
'JCI data explicitly measure PMP22 in S4B, but its exact sequence/tag construct is not established here; no PMP22 coding-mutant/duplication contrast is supplied. Surface and total are fluorescence quantities, not calibrated molecules per viable cell. The HRP source measures a different cargo; neither PMP22 nor RER1/UGGT1/LMAN1 appear as targets in this selected follow-up. The eLife background contains Q01453, but its actual Proteins capture table has no exact PMP22 entry: annotation coverage is not observed expression or a zero effect.',
'',
'HRP has two biological repeats. Golgi images and cells are nested within wells, mostly one well per target. Flow cells are summarized at the reported biological-experiment level: S4 has three values per arm, the variant panel four, and the top-five panel five to thirteen depending on arm. Electrophysiology records cells without experiment-level nesting; no culture-level significance is claimed from those cells. No donor independence is inferred.',
'',
'## Direct PMP22 counter-screen',
'',
f"VU0494372 at 10 uM for 16 h gives PMP22 surface geometric fold {fmt(pmp['geometric_fold'])}, with unpaired log-Welch 95% model interval [{fmt(pmp['fold_95ci'][0])}, {fmt(pmp['fold_95ci'][1])}], n=3 per arm. Total fold is {fmt(j['counter_screen']['PMP22']['total']['geometric_fold'])}; efficiency fold {fmt(j['counter_screen']['PMP22']['fraction_percent']['geometric_fold'])}. No improvement is demonstrated, but this is not proof of no effect/equivalence. All single-observation omissions keep the surface point estimate below one; model uncertainty still permits a moderate increase.",
'',
f"The better-matched transient KCNQ1 S4A surface fold is {fmt(k['geometric_fold'])}. The PMP22-minus-KCNQ1 log2 interaction is {fmt(interaction['effect'])}, model interval [{fmt(interaction['unpaired_model_95ci'][0])}, {fmt(interaction['unpaired_model_95ci'][1])}] if all four groups are independent. Unknown cross-cargo/cross-arm covariance invalidates treating that assumption as established: a covariance sensitivity envelope includes zero. Crucially, PMP22 effects already entered compound selection; this counter-screen is not independent specificity validation. The caption says 0.1% DMSO while both native S4 worksheets say 0.2%; neither label is silently repaired.",
'',
'All five selected KCNQ1 compound contrasts and WT/coding-variant responses are in candidate-contrast-table.tsv, with endpoints kept separate. They do not establish PMP22 rescue. KCNQ1 cell currents are orthogonal same-study evidence, not matched to surface measurements or transferable myelin function. Supplemental Table 2 and native current counts disagree in three control arms; all native numbers are retained, not trimmed to force agreement. At 20 uM the separate viability panel is lower than vehicle, providing an additional context restriction.',
'',
'## General cargo candidates and contradictions',
'',
'Rule: require at least 1.25-fold SN and SN/CL in both repeats. This is a retrospective descriptive rule, not a significance/FDR threshold or ranking of rescue. Controls are matched plate/repeat non-targeting siRNAs after no-cell background subtraction; untreated wells are a separate sensitivity comparator.',
'',
'gene | SN repeat 1/2 | CL repeat 1/2 | SN/CL repeat 1/2 | interpretation',
]
for gene in ['ACSL5','ERVFRD-1','FCF1','PEX2','TMEM220','GPR161','FAM98B','FAM102B','MXRA7']:
    g=genes[gene]
    text='gain rule; unvalidated machinery transfer' if g['gain_rule']=='True' else 'inspect retention versus production; not rescue'
    lines.append(' | '.join([gene,*[fmt(float(g[key+'_repeat1']))+'/'+fmt(float(g[key+'_repeat2'])) for key in ['SN_fold','CL_fold','SN_CL_fold']],text]))
lines += ['', 'Full Cartesian mean/median-background by mean/either-single-NT checks and effect-size threshold sensitivity:', '']
for r in grid:
    lines.append(f"At cutoff {r['cutoff']:.2f}: {r['main_n']} main-normalization candidates; {r['full_NT_background_n']} survive every NT/background combination. Robust names: {', '.join(r['full_NT_background_genes']) or 'none'}.")
lines += [
'',
f"ACSL5's worst tested NT/background SN fold is {fmt(robustness['ACSL5_minimum_SN_across_grid'])}; it sits close to the 1.25 cutoff, so 'robust' should not imply a wide margin. Against untreated controls its SN folds are {fmt(robustness['ACSL5_untreated_comparator']['SN'][0])}/{fmt(robustness['ACSL5_untreated_comparator']['SN'][1])}, and SN/CL {fmt(robustness['ACSL5_untreated_comparator']['SN_CL'][0])}/{fmt(robustness['ACSL5_untreated_comparator']['SN_CL'][1])}; the 1.25 rule fails there. Untreated is not the preferred comparator for siRNA, but this restricts certainty.",
'',
'GPR161 and FAM98B decrease secreted activity in both repeats, but their SN/CL effects reverse sign across repeats. Averaging would conceal that contradiction. TMEM220 more consistently combines lower SN with higher CL, and has an orthogonal Golgi phenotype. A single Golgi well is not replication or proof of an ER-retention mechanism. One FNDC5 image is explicitly na; it stays missing, never measured-zero.',
'',
'## Orthogonal quality-control test',
'',
'Mean percentages of surviving pulse-labeled IGF1R that are mature at 2 h:',
]
for group in ['WT','UGGT1_KO','UGGT2_KO','UGGT1_2_KO','ALG6_KO','ALG6_KO_DNJ','WT_no_DNJ','WT_DNJ']:
    lines.append(f"{group}: {u['pulse'][group]['mean_0_1_2h'][2]:.2f}%.")
lines += [
'',
'UGGT1 loss has a larger point-estimate penalty than UGGT2 loss, but the n=3 unpaired comparison is uncertain; it is not proof of a statistically distinct isoform effect. ALG6 loss and glucosidase inhibition strongly oppose an indiscriminate less-surveillance-is-better model. These native fractions are not absolute surface signal, initial-pulse-normalized delivery yield, IGF1R signaling or PMP22 function. DNJ steady-state mature fractions were independently calculated from pro/mature band intensities without executing source formulas. A numeric N57 cell displayed as a date was read from its literal OOXML token 51.53951086478984.',
'',
'## Novelty, independent validation and falsification',
'',
'The VU0494372/PMP22 counter-screen and UGGT maturation findings were already reported. ACSL5 values were already in the published HRP data. The contribution here is a full-universe endpoint and repeat-sensitivity analysis that nominates an incidental assay-level lead and rejects overbroad interpretation, not a verified new biological mechanism.',
'',
'An actual primary-source novelty check found that intestine-specific Acsl5 loss already increases postprandial GLP-1/PYY in mice (PMC10990902, Fig 7), with altered fatty-acid sensing proposed. A different primary study reports reduced radiolabeled TAG secretion after ACSL5 depletion in rat hepatocytes (PMC2952567, Fig 3F). These are independent context observations, not new computations here: hormone concentration and lipid export are not constitutive protein-cargo delivery. They neither validate the frozen protein-cargo prediction nor support a universal secretion enhancer. They specifically motivate lipid/substrate sensing as an alternative to transport machinery.',
'',
'Frozen prediction blob 32f44b839b162178cf551b8b8e846a1ecd09ceb0eb10cc02084347ab2d7d0e11 preceded independent outcome acquisition attempts. The independent human cargo RNAi source ncb2510 remained inaccessible after documented alternatives, so ACSL5 transfer is unevaluated, not validated or falsified. An additional VCP/PGD study supplied primary text but not usable native XLSX files; no numerical conclusion is invented from those failures. The source-locators file preserves actual responses, including HTTP 200 error/challenge bodies. Search counts and returned scope are in novelty-validation-audit.json; absence from a title/abstract query is not a novelty proof.',
'',
'## Discriminating prediction and stopping point',
'',
notes['next_discriminating_question'],
'',
'A positive mass-delivery result with unchanged/controlled synthesis and viability would support handling. Loss of the effect in an independent cargo or in direct protein mass, despite increased HRP activity, would reject generic transport enhancement. WT PMP22, overdosage and coding mutants remain separate follow-ups. Functional myelin incorporation remains unmeasured.',
'',
f"The bounded analysis is complete: {len(table)} endpoint-specific rows, full selected HRP universe, native measurements, source hashes, producer receipts and {v['n_checks']} separately implemented computational checks. Checks verify calculations, not independent biology. No raw MS processing, downloaded scientific code, workbook formulas, macros or pickle/R serializations were executed. Open dependencies are independent protein-cargo validation and any downstream PMP22/function transfer, not completion of these available-data analyses.",
'',
'Artifacts from the quantitative milestone:']
for path in sorted((OUT/'registrations').glob('*.json')):
    if '.readback.' not in path.name:
        r=json.loads(path.read_text())
        if 'artifact' in r:
            lines.append(path.stem+': '+r['artifact'])
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
summary={'endpoint_rows':len(table),'hrp_targets':len(genes),'threshold_grid':grid,'native_measurement_records_including_reused_controls':load('analysis-validation.json')['native_measurements'],'checks':v['n_checks'],'published_milestone':'post_910fc4d8914a4a32ae441c8481e020c7','valid':True}
write_json('report-validation.json',summary)
print(json.dumps(summary,indent=2))
