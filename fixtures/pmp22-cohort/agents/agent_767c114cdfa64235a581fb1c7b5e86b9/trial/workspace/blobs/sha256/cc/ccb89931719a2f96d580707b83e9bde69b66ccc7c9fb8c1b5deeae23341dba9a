"""Audit full native processed backgrounds and test the frozen PMP22 PUM prediction.

No raw sequencing processing, fitted-count reconstruction, formula evaluation, or
cross-cell meta-analysis. Source Cuffdiff test_stat is NOT interpreted as a Wald z.
"""
import csv
import gzip
import hashlib
import io
import json
import math
import os
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from statistics import NormalDist
import zipfile

import openpyxl

Q = Path(__file__).resolve().parents[1]
W = Path(os.environ['BIO_WORKSPACE'])
OUTPUT = Q / 'outputs/independent-r001'
OUTPUT.mkdir(exist_ok=True)
inputs = []
backgrounds = []
targets = []
controls = []
all_rows = []
ratio_warnings = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(name, value):
    def source_type(x):
        if isinstance(x, (date, datetime, time)):
            return {'native_type': type(x).__name__, 'source_value': x.isoformat()}
        raise TypeError(type(x).__name__)
    (OUTPUT / name).write_text(json.dumps(value, indent=2, allow_nan=False, default=source_type))


def input_file(path, role):
    data = path.read_bytes()
    inputs.append({'path': str(path.relative_to(Q)), 'sha256': digest(data), 'bytes': len(data), 'role': role})
    return data


def archive(label):
    rp = Q / 'inputs/http' / (label + '.receipt.json')
    receipt = json.loads(input_file(rp, 'native HTTP receipt'))
    payload = input_file(Q / 'inputs/http' / (label + '.payload'), 'native supplemental archive')
    assert receipt['status'] == 200 and receipt['complete']
    assert receipt['sha256'] == digest(payload)
    return zipfile.ZipFile(io.BytesIO(payload))


def number(value):
    if value is None or value in ('NA', '', 'nan', 'NaN', 'Inf', '-Inf', '=-inf', '=inf'):
        return None
    if isinstance(value, str) and value.startswith('='):
        return None  # Never execute spreadsheet formulas.
    result = float(value)
    return result if math.isfinite(result) else None


def rows_of(wb, name):
    sheet = wb[name]
    sheet.reset_dimensions()
    return [list(r) for r in sheet.iter_rows(values_only=True) if any(v is not None for v in r)]


def result_row(study, context, perturbation, endpoint, gene, effect, p, qvalue, se=None, **extra):
    r = {'study': study, 'context': context, 'perturbation': perturbation, 'endpoint': endpoint,
         'gene': gene, 'log2_effect': number(effect), 'pvalue': number(p), 'source_padj': number(qvalue),
         'lfcSE': number(se), 'ci95_lower': None, 'ci95_upper': None,
         'uncertainty': 'Source adjusted p only; no SE supplied; no reconstructed CI', **extra}
    if r['lfcSE'] is not None and r['log2_effect'] is not None:
        e, s = r['log2_effect'], r['lfcSE']
        z = NormalDist().inv_cdf(0.975)
        r.update(ci95_lower=e-z*s, ci95_upper=e+z*s, uncertainty='Nominal normal/Wald interval; not simultaneous or selection-adjusted')
    r['fold_effect'] = 2**r['log2_effect'] if r['log2_effect'] is not None else None
    if gene == 'PMP22':
        targets.append(r)
    elif gene in {'PUM1', 'PUM2', 'CNOT1', 'CNOT7', 'CNOT8', 'CCNG2'}:
        controls.append(r)
    return r


# Freeze/check the prediction's bytes rather than replace its rule after inspection.
prediction_path = Q / 'outputs/predictions/pmp22-pum-persistence-r001.json'
prediction_bytes = input_file(prediction_path, 'sealed before target-table inspection')
assert digest(prediction_bytes) == 'd3623d23b558af6a5fd2a7228c91a86dd96fe494f8097f09f794e5d2a7f4b951'

# HEK293: author-deposited coefficients, not a refit of raw or processed counts.
arc = archive('pum-bruchase-supp-r001')
member = 'supp_077362.120_Supplemental_Bru_seq_and_BruChase_seq_model_coefficients.tsv'
source = arc.read(member)
(OUTPUT / 'bruchase-native-coefficients.tsv').write_bytes(source)
bru = list(csv.DictReader(io.StringIO(source.decode()), delimiter='\t'))
assert len({r['Gene'] for r in bru}) == len(bru)
terms = {'relative_labeled_RNA_persistence': 'conditiontime_interaction_term_',
         'nascent_RNA_abundance': 'siPUM_vs_siNTC_condition_term_'}
for endpoint, prefix in terms.items():
    for r in bru:
        x = result_row('GSE145237', 'HEK293', 'PUM1+PUM2 siRNA', endpoint, r['Gene'],
                       r[prefix+'log2FoldChange'], r[prefix+'pvalue'], r[prefix+'padj'], r[prefix+'lfcSE'],
                       source_member=member, source_status='source_padj_present' if r[prefix+'padj'] != 'NA' else 'source_padj_NA_not_zero',
                       assembly='hg19', unit='Four biological culture replicates per arm/time; 48h RNAi, 30min BrU, 0/6h chase')
        all_rows.append(x)
    backgrounds.append({'study': 'GSE145237', 'endpoint': endpoint, 'all_source_genes': len(bru),
                        'finite_effect': sum(number(r[prefix+'log2FoldChange']) is not None for r in bru),
                        'finite_pvalue': sum(number(r[prefix+'pvalue']) is not None for r in bru),
                        'source_padj_present': sum(number(r[prefix+'padj']) is not None for r in bru),
                        'source_padj_NA': sum(number(r[prefix+'padj']) is None for r in bru),
                        'genes': [r['Gene'] for r in bru]})
fields = ['log2FoldChange', 'lfcSE', 'stat', 'pvalue', 'padj']
duplicate_columns = {f: sum(r['sixhr_vs_zerohr_time_term_'+f] == r['conditiontime_interaction_term_'+f] for r in bru) for f in fields}
features_zip = zipfile.ZipFile(io.BytesIO(arc.read('supp_077362.120_Supplemental_features_for_machine_learning.zip')))
features = list(csv.DictReader(io.StringIO(features_zip.read('features_for_machine_learning.tsv').decode()), delimiter='\t'))
feature_target = [r for r in features if r['Gene'] == 'PMP22']
assert len(feature_target) == 1
feature_target = feature_target[0]
feature_reduced = {k: v for k, v in feature_target.items() if k in {'Gene', 'effect'} or k.endswith('bound') or 'pum1_pre_new' in k or 'pum2_pre_new' in k or 'regex_loose' in k or 'bound' in k.lower()}
interaction = next(r for r in targets if r['study'] == 'GSE145237' and r['endpoint'] == 'relative_labeled_RNA_persistence')
state = 'untestable' if interaction['source_padj'] is None or interaction['lfcSE'] is None else ('supported' if interaction['log2_effect'] > 0 and interaction['source_padj'] <= 0.05 else 'failed')
prediction = {'candidate_id': 'pmp22-pum-persistence', 'prediction_artifact_or_file': str(prediction_path.relative_to(Q)),
              'prediction_sha256': digest(prediction_bytes), 'status': state,
              'observed': interaction, 'source_feature_class': feature_target['effect'],
              'interpretation': 'Frozen positive-FDR prediction fails on the deposited interaction. Not directional falsification or no-effect proof. Source NOEFFECT class is specific to the paper 1.75-fold practical-equivalence rule.',
              'source_export_warning': 'All time-term columns exactly duplicate interaction-term columns. Report interaction as deposited, corroborated by source feature classification, not a verified independent refit. No baseline decay rate inferred.'}

# HCT116: gene-summary rows occur once; additional exon rows must not inflate n.
arc = archive('pum-cnot-supp-r001')
member = 'supp_078436.120_Supplemental_Table_S2.xlsx'
wb = openpyxl.load_workbook(io.BytesIO(arc.read(member)), read_only=True, data_only=False)
hct_sheets = ['PUM1 RNAi', 'PUM2 RNAi', 'PUM1&2 RNAi', 'CNOT1 RNAi', 'CNOT7&8 RNAi']
hct_native = {}
for sheet in hct_sheets:
    rows = rows_of(wb, sheet)
    header = rows[1]
    assert header[1] == 'Gene Name' and header[5] == 'pAdj'
    # Repeated gene names with columns 2:7 empty are exon-detail rows, not
    # extra gene observations. Source dates/numeric symbols are unresolved
    # identifiers and are retained by source row ID, never repaired to genes.
    genes = [r for r in rows[2:] if len(r) > 6 and r[1] is not None and any(v is not None for v in r[2:7])]
    assert all(isinstance(r[1], str) or isinstance(r[1], (datetime, int)) for r in genes)
    valid_names = [r[1] for r in genes if isinstance(r[1], str)]
    assert len(set(valid_names)) == len(valid_names)
    hct_native[sheet] = {'header': header, 'nonempty_rows': rows[2:]}
    for r in genes:
        gene = r[1] if isinstance(r[1], str) else 'UNRESOLVED_SOURCE_ROW_' + str(r[0])
        x = result_row('GSE159510', 'HCT116', sheet, 'polyadenylated_gene_RNA_abundance', gene, r[4], None, r[5],
                       source_identifier_type=type(r[1]).__name__, source_identifier_token=str(r[1]),
                       control_mean=r[2], intervention_mean=r[3], source_status=r[6],
                       splicing_APA_flag=r[7], tandem_APA_flag=r[8], source_member=member, source_sheet=sheet,
                       assembly='hg38 / GENCODE32', unit='Three biological culture replicates per condition, 48h RNAi',
                       source_scale_note='Single-PUM sheets label Fold Change, but signed values and primary methods establish log2 scale; retained native labels.')
        all_rows.append(x)
    backgrounds.append({'study': 'GSE159510', 'contrast': sheet, 'nonempty_rows_without_two_header_rows': len(rows)-2,
                        'gene_summary_rows': len(genes), 'exon_detail_rows': len(rows)-2-len(genes),
                        'unresolved_nonstring_identifiers': sum(not isinstance(r[1], str) for r in genes),
                        'source_status_counts': dict(Counter(r[6] for r in genes)),
                        'genes': [r[1] if isinstance(r[1], str) else {'source_row': r[0], 'type': type(r[1]).__name__, 'value': str(r[1])} for r in genes]})
wb.close()
save_json('hct116-native-sheet-values.json', hct_native)

# TCam-2: keep full Cuffdiff statuses and reverse source log2(control/KD).
arc = archive('pum-tcam-supp-r001')
inner = zipfile.ZipFile(io.BytesIO(arc.read('cells-09-00984-s001.zip')))
inner = zipfile.ZipFile(io.BytesIO(inner.read('FINAL Supplementary Files.zip')))
tcam_native = {}
for table_no in (7, 9):
    choices = [n for n in inner.namelist() if '/Table S'+str(table_no)+' ' in n and n.endswith('.xlsx')]
    assert len(choices) == 1
    member = choices[0]
    wb = openpyxl.load_workbook(io.BytesIO(inner.read(member)), read_only=True, data_only=False)
    for sheet in wb.sheetnames:
        if not sheet.startswith('Cuffdiff_'):
            continue
        rows = rows_of(wb, sheet)
        header = rows[0]
        assert header[:4] == ['test_id', 'gene_id', 'gene', 'locus']
        data = [dict(zip(header, r, strict=False)) for r in rows[1:]]
        tcam_native[sheet] = data
        assert all(isinstance(r['test_id'], str) for r in data)
        assert len({str(r['test_id']) for r in data}) == len(data)
        for r in data:
            p, s2 = r['sample_1'], r['sample_2']
            assert isinstance(p, str) and isinstance(s2, str)
            native = number(r['log2(fold_change)'])
            if table_no == 9:
                assert p in {'siPUM1','siPUM2'} and s2 == 'siCTRL'
                effect, numerator, denominator = (-native if native is not None else None), r['value_1'], r['value_2']
                endpoint = 'conditional_RNA_abundance_after_4h_ActD'
                perturbation = p
            else:
                endpoint = 'RIP_enrichment'
                if p in {'RIP-PUM1','RIP-PUM2'}:
                    effect, numerator, denominator = (-native if native is not None else None), r['value_1'], r['value_2']
                    perturbation = p + '/' + s2
                else:
                    assert p == 'TCAM2' and s2 in {'RIP-PUM1','RIP-PUM2'}
                    effect, numerator, denominator = native, r['value_2'], r['value_1']
                    perturbation = s2 + '/' + p
            ratio_error = None
            if number(numerator) and number(denominator) and effect is not None:
                ratio_error = abs(math.log2(float(str(numerator))/float(str(denominator)))-effect)
                if ratio_error >= 0.003:
                    ratio_warnings.append({'sheet': sheet, 'source_row': r, 'absolute_log2_ratio_discrepancy': ratio_error})
                # Target/control direction must validate. Other malformed native
                # rows are retained and flagged, not silently fixed or dropped.
                if r['gene'] in {'PMP22', 'PUM1', 'PUM2'}:
                    assert ratio_error < 0.003
            x = result_row('GSE123016', 'TCam-2', perturbation, endpoint, r['gene'], effect, r['p_value'], r['q_value'],
                           source_log2_ratio_discrepancy=ratio_error,
                           source_status=r['status'], numerator_fpkm=numerator, denominator_fpkm=denominator,
                           native_log2_source_sample2_over_sample1=r['log2(fold_change)'], source_test_stat=r['test_stat'],
                           source_member=member, source_sheet=sheet, source_row_id=r['test_id'], source_locus=r['locus'],
                           assembly='hg19, Cufflinks locus annotation',
                           unit='Three biological culture replicates per arm; RNAi 72h with final 4h ActD; RIP separate experiment')
            all_rows.append(x)
        backgrounds.append({'study': 'GSE123016', 'contrast': sheet, 'source_loci': len(data),
                            'source_status_counts': dict(Counter(r['status'] for r in data)),
                            'feature_ids': [r['test_id'] for r in data]})
    wb.close()
save_json('tcam-native-cuffdiff.json', tcam_native)

# Verification of acquired sample files is inventory, not independent replication.
manifest_bytes = input_file(Q/'inputs/independent/tcam-native-inputs.json', 'native sample acquisition manifest')
manifest = json.loads(manifest_bytes)
sample_inventory = []
for m in manifest:
    rec = m['acquisition']
    assert rec['outcome'] == 'available_full'
    blob = rec['blob']
    data = (W/'blobs/sha256'/blob[:2]/blob).read_bytes()
    assert len(data) == rec['bytes'] and digest(data) == blob
    text = gzip.decompress(data).decode()
    raw_header = text.splitlines()[0]
    if m['name'] == 'GSM3490752_RIP-Seq_PUM2_1.txt.gz':
        assert raw_header == 'RefSeq_id FPKM'
        parsed = [line.split() for line in text.splitlines()]
        parse_rule = 'Observed whitespace-delimited file; native header retained verbatim'
    else:
        parsed = list(csv.reader(io.StringIO(text), delimiter='\t'))
        expected = 'RefDeq_ID' if m['name'] == 'GSM3490764_Tcam2_transctiptome-1.txt.gz' else 'RefSeq_ID'
        assert parsed[0] == [expected, 'FPKM']
        parse_rule = 'Observed tab-delimited file; RefDeq_ID source-header spelling is retained, not rewritten'
    rows = parsed[1:]
    assert all(len(r) == 2 for r in rows)
    sample_inventory.append({'name': m['name'], 'blob': blob, 'rows': len(rows),
                             'source_header': raw_header, 'parse_rule': parse_rule,
                             'unique_refseq': len({r[0] for r in rows}),
                             'measured_zero_rows': sum(float(r[1]) == 0 for r in rows),
                             'role': 'coverage inventory; unversioned RefSeq sample values are not summed or independently tested'})
# Sample identities and primary methods are essential provenance, not new outcomes.
for name in ['GSE123016','GSE159510']:
    data = json.loads(input_file(Q/'inputs/independent'/(name+'-sample-map.json'), 'native sample metadata'))
    save_json(name+'-sample-units.json', {k: v['Sample_title'] for k,v in data.items()})
for label in ['pum-tcam-paper-r001','pum-cnot-paper-r001','nrg1-pum-bruchase-paper-r001']:
    input_file(Q/'inputs/http'/(label+'.receipt.json'), 'primary-paper HTTP receipt')
    input_file(Q/'inputs/http'/(label+'.payload'), 'primary-paper native XML')

# Joint criteria never change after a tempting partial result.
binding = []
for rbp in ['PUM1', 'PUM2']:
    rip = [r for r in targets if r['study']=='GSE123016' and r['endpoint']=='RIP_enrichment' and r['perturbation'].startswith('RIP-'+rbp+'/')]
    assert len(rip) == 2
    kd = next(r for r in targets if r['study']=='GSE123016' and r['perturbation']=='si'+rbp)
    strict_bound = all(r['log2_effect'] is not None and r['log2_effect'] >= 1 and r['source_padj'] <= .05 for r in rip)
    binding.append({'rbp': rbp, 'context': 'TCam-2', 'rip_comparisons': rip,
                    'source_twofold_binding_necessary_conditions_pass': strict_bound,
                    'all_three_replicates_enriched': 'not independently adjudicated',
                    'abundance_response_source_q_pass': kd['source_padj'] <= .05,
                    'joint_strict_candidate': strict_bound and kd['source_padj'] <= .05,
                    'interpretation': 'IgG enrichment is not sufficient for source strict binding selection; total transcriptome comparison retained.'})
summary = {'question': Q.name, 'prediction': prediction, 'target_results': targets, 'controls': controls,
           'tcam_binding_adjudication': binding, 'bruchase_PMP22_feature_annotations': feature_reduced,
           'tcam_source_ratio_warnings': ratio_warnings,
           'bruchase_all_time_and_interaction_identical_counts': duplicate_columns,
           'sample_file_inventory': sample_inventory,
           'background_counts': [{k:v for k,v in r.items() if k not in {'genes','feature_ids'}} for r in backgrounds],
           'limitations': ['Independent cell contexts, not independent repetitions of an identical contrast.',
                          'PUM1/PUM2 contrasts within each study can share controls; no meta-analysis or sign-count test.',
                          'No target-specific CNOT binding assay; CNOT abundance effects do not establish PUM mediation.',
                          'No Schwann perturbation or expressed transcript-site availability established.',
                          'Source normalized relative outcomes, not promoter initiation, direct mediation or absolute half-lives.',
                          'HCT116 and TCam target rows were exposed before this executed audit; retrospective evidence.',
                          'BruChase duplication is retained as a source export limitation; the unreported baseline time term cannot be recovered here.']}
save_json('summary.json', summary)
save_json('complete-backgrounds.json', backgrounds)
save_json('input-manifest.json', inputs)
save_json('prediction-result.json', prediction)
columns = sorted(set().union(*(r.keys() for r in all_rows)))
for name, rows in [('all-feature-endpoints.tsv',all_rows), ('PMP22-endpoints.tsv',targets), ('perturbation-controls.tsv',controls)]:
    with (OUTPUT/name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter='\t', extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)
print('PREDICTION', state, 'source class', feature_target['effect'])
for r in targets:
    print(r['study'],r['perturbation'],r['endpoint'],r['log2_effect'],r['ci95_lower'],r['ci95_upper'],r['source_padj'])
print('BACKGROUND', summary['background_counts'])
print('ALL_ROWS', len(all_rows), 'TARGET_ROWS', len(targets), 'STRICT_TCAM', [(r['rbp'],r['joint_strict_candidate']) for r in binding])
