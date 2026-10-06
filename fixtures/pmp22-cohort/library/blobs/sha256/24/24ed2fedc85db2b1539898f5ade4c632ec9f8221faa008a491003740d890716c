"""Compile source-backed eligibility judgments and independently validate numerical outputs."""
import csv
import gzip
import hashlib

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'
PUB = ROOT/'inputs'/'public'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def table(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, delimiter='\t')
        w.writeheader()
        w.writerows(rows)


s = json.loads((OUT/'stress-audit-summary.json').read_text())
j = json.loads((ROOT/'inputs'/'context-judgments.json').read_text())
r = json.loads((OUT/'execution-r002.json').read_text())
assert r['exit_code'] == 0 and r['complete'] and r['code_unchanged']
assert sha(ROOT/'scripts'/'analyze_stress.py') == r['code_sha256']
for item in r['outputs']:
    assert item['written'] and sha(OUT/Path(item['path']).name) == item['sha256']

samples = list(csv.DictReader((OUT/'sample-assay-eligibility.tsv').open(), delimiter='\t'))
assert len(samples) == len({r['accession'] for r in samples}) == s['sample_labels']
assert s['sample_counts_by_series'] == {'GSE103667':8,'GSE118660':13,'GSE90070':32}
# Independently verify target footprint native cells and ratios using csv and math.
for result in s['footprint']:
    p = PUB/f'GSE118660_{result["cell"]}_tpm.txt.gz'
    with gzip.open(p,'rt') as f:
        native = next(row for row in csv.DictReader(f,delimiter='\t') if row['Gene_Id']=='Pmp22')
    treated, control = result['contrast'].split('/')
    expected = math.log2(float(native[treated])/float(native[control]))
    assert math.isclose(expected,result['native_tpm_log2'],abs_tol=1e-12)

with gzip.open(PUB/'GSE90070_dataCount.csv.gz','rt') as f:
    count_rows = list(csv.DictReader(f))
target = next(x for x in count_rows if x['']=='Pmp22')
assert min(float(v) for k,v in target.items() if k) == s['fraction']['target_min_count_all_samples']
for row in csv.DictReader((OUT/'fraction-target-native-cells.tsv').open(),delimiter='\t'):
    assert float(target[row['source_column']]) == float(row['Pmp22_raw_count'])
for row in s['fraction']['contrasts']:
    assert math.isclose(row['polysome_log2_change']-row['cytosolic_log2_change'],row['relative_loading_interaction_log2'],abs_tol=1e-12)
    assert math.isclose(sum(row['treated_loading'])/4-sum(row['control_loading'])/4,row['relative_loading_interaction_log2'],abs_tol=1e-12)

with gzip.open(PUB/'GSE103667_TE.norm.txt.gz','rt') as f:
    native_te = list(csv.DictReader(f,delimiter='\t'))
native_target = [x for x in native_te if x['name']=='Pmp22']
assert native_target == s['TE']['target_native_rows']
assert len(native_target)==7
vectors = {tuple(x[c] for c in ['TE.DMSO1','TE.THAP1','TE.DMSO2','TE.THAP2']) for x in native_target}
assert len(vectors)==4
assert all(float(x['TE.THAP1']) < float(x['TE.DMSO1']) and float(x['TE.THAP2']) < float(x['TE.DMSO2']) for x in native_target)

primary = {x['contrast']: x for x in s['fraction']['contrasts'] if x['normalization']=='assay_separate_median_ratio'}
foot = {(x['cell'],x['contrast']):x for x in s['footprint']}
contexts = j['contexts']
for row in contexts:
    if row['id'] == 'GSE118660_MEF_WT':
        row['observed'] = [x for x in s['footprint'] if x['cell']=='MEF']
    elif row['id'] == 'GSE118660_NIH3T3':
        row['observed'] = [x for x in s['footprint'] if x['cell']=='3t3']
    elif row['id'] == 'GSE90070_acute':
        row['observed'] = [primary['Tg1/Ctrl']]
    elif row['id'] == 'GSE90070_chronic':
        row['observed'] = [primary['Tg16/Ctrl'],primary['Tg16/Tg1']]
    elif row['id'] == 'GSE90070_late_PERKi':
        row['observed'] = [primary['Tg16+PERKi/Tg16']]
    else:
        row['observed'] = s['TE']['target']
dump('stress-context-replication-matrix.json',j)
table('stress-context-replication-matrix.tsv',[{k:v for k,v in x.items() if k!='observed'} for x in contexts])
blocker = {'conclusion':'No valid calibrated selective-synthesis test in the audited source pairings; retrospective relative-assay diagnostics only.',
           'missing_for_opposed_contexts':['Matched total RNA in GSE118660','Independent culture-level replication at matched time/dose','RPF recovery/per-cell global calibration','PMP22-specific completed nascent protein and residence-time control'],
           'existing_partial_measurements':{'GSE103667':'Split-lysate RNA/RPF supported; processed TE reduces in both labelled replicates but export transform and counts cannot be independently checked from TE.norm alone; normalization is not absolute.',
                                          'GSE90070':'Paired input/heavy-polysome fractions and study-global 35S/half-transit assays; no target/sample calibration. Additional chronic polysome loss tracks RNA.'},
           'identifiability':j['identifiability'], 'next_discriminating_test':j['next_discriminating_test'],
           'negative_result':'Tg16h/Tg1h relative-loading change near zero is not equivalence and not proof that translation never changes.',
           'claim_revision':'Opposed relative RPF changes reject a same-direction relative-occupancy rule, not a universal reduction of absolute synthesis.',
           'exposure':'All target directions were inherited/exposed; computation is native-source replication, not independent biological validation or novelty.'}
dump('selective-translation-blocker.json',blocker)

# Full declared control panel: absence kept distinct from a native zero/low count.
panel = json.loads((ROOT/'inputs'/'analysis-plan-r001.json').read_text())['control_panel']
control_rows = []
for file, delimiter, field in [('GSE118660_MEF_tpm.txt.gz','\t','Gene_Id'),('GSE118660_3t3_tpm.txt.gz','\t','Gene_Id'),('GSE90070_dataCount.csv.gz',',','')]:
    with gzip.open(PUB/file,'rt') as f:
        rows = list(csv.DictReader(f,delimiter=delimiter))
    indexed = {r[field]:r for r in rows}
    for gene in panel:
        rr = indexed.get(gene)
        vals = [float(v) for k,v in rr.items() if k!=field] if rr else []
        control_rows.append({'source':file,'gene':gene,'present_in_native_table':rr is not None,
                             'native_minimum':min(vals) if vals else None,
                             'native_maximum':max(vals) if vals else None,
                             'native_zero_cells':sum(v==0 for v in vals) if vals else None,
                             'meaning':'native values, not an absolute abundance or invariant-control claim' if rr else 'not present in native export; not a biological zero'})
table('control-panel-eligibility.tsv',control_rows)

m = foot[('MEF','PERK_WT_Tg2hr/PERK_WT_Control')]
n = foot[('3t3','NIH3T3_Tg2hr/NIH3T3_Cont')]
progress = primary['Tg16/Tg1']
acute = primary['Tg1/Ctrl']
chronic = primary['Tg16/Ctrl']
rescue = primary['Tg16+PERKi/Tg16']
report = f'''PMP22 stress-context replication and synthesis-identifiability audit

Question q_4280e55151994ef8; agent_a61dee306f4e4c62ba2ac212a5c61a17.

Answer
Opposed relative-footprint responses reproduce in the original source, but do not identify opposite translation efficiencies or absolute synthesis rates. This narrows the progenitor's wording: a universal reduction in absolute synthesis is not rejected by these relative data. No cause of the reversal (RNA, initiation, elongation, global normalization) is identified here.

Executed native-source replication (not independent biological replication)
GSE118660 2h Tg/control, Pmp22:
  MEF WT, 1 uM: TPM {m['control_tpm']} -> {m['stress_tpm']}; log2 {m['native_tpm_log2']:+.4f}.
  NIH3T3, 200 nM: TPM {n['control_tpm']} -> {n['stress_tpm']}; log2 {n['native_tpm_log2']:+.4f}.
  Compositional expected-count summaries retain the opposed signs: CPM {m['expected_count_cpm_log2']:+.4f}/{n['expected_count_cpm_log2']:+.4f}; median-ratio {m['expected_count_median_log2']:+.4f}/{n['expected_count_median_log2']:+.4f}.
Each native footprint matrix has {m['feature_rows']} gene rows. Counts are RSEM expected-count exports even though numeric entries are integer-valued; they are not relabelled raw reads. Both cell model and Tg dose change, alongside culture supplements. One library per condition/time is not replicated causal context evidence. GEO's RNA-Seq strategy and generic extraction text do not supply missing matched RNA.

GSE90070: {s['fraction']['native_gene_rows']} native gene rows, four condition groups and sixteen within-preparation Input/heavy-polysome pairs. Pmp22 minimum native count across libraries: {s['fraction']['target_min_count_all_samples']:.0f}. Input is cytosolic RNA and H is >4-ribosome RNA, not RPF. Primary normalization estimates median ratios separately within the two assays, excludes Pmp22, and uses a 0.5 native-count pseudocount. No cross-condition pairing is invented.
  1h/control: RNA {acute['cytosolic_log2_change']:+.4f}, H {acute['polysome_log2_change']:+.4f}; relative H/Input interaction {acute['relative_loading_interaction_log2']:+.4f} log2.
  16h/control: RNA {chronic['cytosolic_log2_change']:+.4f}, H {chronic['polysome_log2_change']:+.4f}; interaction {chronic['relative_loading_interaction_log2']:+.4f}.
  16h/1h progression: RNA {progress['cytosolic_log2_change']:+.4f}, H {progress['polysome_log2_change']:+.4f}; interaction {progress['relative_loading_interaction_log2']:+.4f}.
  Late PERKi/Tg16h: RNA {rescue['cytosolic_log2_change']:+.4f}, H {rescue['polysome_log2_change']:+.4f}; interaction {rescue['relative_loading_interaction_log2']:+.4f}.
Joint median-ratio and CPM sensitivities are retained. Chronic progression's additional polysome decline is RNA-congruent at this relative endpoint. Near zero is not equivalence. No biological p value is reported: preparation pairing is verified, but independently prepared culture/donor IDs are unresolved. Sample-deletion ranges in the JSON are sensitivity ranges, not confidence intervals. This recovers an existing source interpretation: PMC5730339 P23 explicitly calls PMP22 congruently regulated.

Important correction to a blanket missing-assay claim
PMC5730339 does include global 35S Met/Cys incorporation (P32) and ribosome half-transit measurements (P36; global 1h/12h comparison in P10). They do not supply per-RNAseq-library recovery factors or target-specific PMP22 completed-synthesis/elongation rates. GSE118660 similarly includes global polysome profiles and reports modest genome-wide 5-prime footprint accumulation (PMC6416471 Par12). These measurements inform mechanisms but cannot be silently converted into target calibration.

GSE103667 matched RNA/RPF opportunity and limit
PMC6359928 P58 explicitly splits lysate supernatant for RNA and footprint libraries. Eight accession labels map to two conditions, two assays and two replicate labels. Seven Pmp22 RefSeq rows represent four distinct numerical vectors, not seven biological replicates. All rows decrease in both replicate labels. A target-only decrease is not selective repression: broad background TE also declines. The paper describes log10 TE (P61) while GEO TE.norm does not explicitly label the export transform; conditional linear-versus-log10 conversions are retained as alternatives, neither claimed as the identified fold. GEO's >=10 RNA-read rule and paper's >=50 any-read rule remain distinct. Constituent sample-level counts are not in the inspected TE.norm table. Bedgraphs are available but no reprocessing was substituted for missing calibration. The contradictory human-kidney cell-type field is preserved; organism, NIH3T3 line, mm9 and paper identify the intended mouse context.
The RNA-granule branch's Drosophila spike-ins are not RPF spike-in calibration. Total-sequenced-read normalization is not completed protein per cell per time.

Deliverable and stopping boundary
The machine-readable matrix covers {len(contexts)} judged contexts and {s['sample_labels']} accession labels, not that many independent biological units. Sample maps, native target cells, broad backgrounds, control-panel detection, two producing receipts, input hashes and source-specific contradictions are retained. No calibrated paired-RNA/RPF/nascent-PMP22 test passes eligibility. The blocker artifact specifies exactly what is missing; the proposed matched-cell/dose factorial experiment keeps RNA, relative occupancy, elongation and completed synthesis distinct. A steady-flow identity explains the limit: J_t/J_c = (F_t/F_c)*(Z_t/Z_c)*(tau_c/tau_t). Unknown global footprint scale Z and residence time tau prevent inference of completed flux J from relative footprints F.

Community reuse and provenance
Forum searches preceded collection and included mechanisms, assays and datasets, not only PMP22. Corrected upstream map/report and current RNA-fate/proteostasis results changed the decision: do not rediscover known reversed footprints, join DTT/RIDD to Tg as matched data, or treat total/surface protein as synthesis. The selectively fetched upstream package and RNA-fate assay matrix are marked reused. The prior researcher's selective stress handoff is an open provenance dependency, not necessary for the source audit to finish. No imported scientific code was run and no raw sequencing processed.

Failures preserved
EuropePMC fullTextXML HTTP500, article HTML HTTP403, PMC HTTP200 challenge content, and web_extract backend error were observed. NCBI efetch successfully supplied both missing primary XMLs. No browser corroboration is claimed. First analysis invocation failed because Pmp22 has multiple TE vectors, not one gene-level vector. The corrected producer retains all native RefSeq rows rather than choosing one, and execution-r002 completed. All inherited failed/untestable tests listed in LABBOOK remain unchanged. This is not novel biology, human/Schwann transfer, or an independent synthesis experiment.
'''
(OUT/'REPORT.txt').write_text(report)
validation = {'status':'passed','sample_labels':len(samples),'unique_accessions':len({x['accession'] for x in samples}),
              'contexts':len(contexts),'Pmp22_TE_native_rows':len(native_target),'Pmp22_TE_distinct_vectors':len(vectors),
              'source_cell_exact_checks':True,'independent_footprint_calculation':True,
              'fraction_interaction_algebra':True,'producer_and_output_hashes':True,
              'source_values_not_invented':True,'descriptive_not_confirmatory':True,
              'no_calibrated_synthesis_test_eligible':True,
              'compiled_outputs':{name:sha(OUT/name) for name in ['stress-context-replication-matrix.json','stress-context-replication-matrix.tsv','selective-translation-blocker.json','control-panel-eligibility.tsv','REPORT.txt']}}
dump('compilation-validation.json',validation)
print(json.dumps(validation,indent=2))
