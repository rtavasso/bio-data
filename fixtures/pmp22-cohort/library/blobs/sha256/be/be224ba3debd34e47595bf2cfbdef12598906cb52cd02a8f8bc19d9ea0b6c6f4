"""Selective unchanged evidence export; metadata/byte checks only, no scientific rerun."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OLD = W / 'questions/q_277f20df4b6b47cc'
OUT = Q / 'outputs'
MEMBERS = {}
FILES = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def enc(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def blob(h):
    data = (W / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    return data


def add(member, data, origin, **extra):
    assert member not in MEMBERS
    MEMBERS[member] = data
    row = dict(member=member, sha256=sha(data), bytes=len(data), origin=origin, **extra)
    FILES.append(row)
    return row


source_names = ['GSE118660_MEF-counts.txt.gz', 'GSE118660_MEF-tpm.txt.gz',
                'GSE118660_3t3-TPM.txt.gz', 'GSE90070_dataCount.csv.gz',
                'GSE118660.soft', 'GSE118660-samples.soft', 'GSE90070.soft',
                'GSE90070-samples.soft', 'PMC6416471.xml', 'PMC5730339.html']
transport_path = OLD / 'inputs/iteration/transport.json'
transport = json.loads(transport_path.read_text())
receipt_records = []
allowed = {'url', 'final_url', 'path', 'status', 'http_status', 'bytes', 'sha256',
           'started', 'finished', 'content_type', 'error', 'accounting_note'}
for name in source_names:
    rel = 'inputs/iteration/' + name
    data = (OLD / rel).read_bytes()
    receipts = []
    for i, entry in enumerate(transport['entries']):
        if entry.get('path') == rel:
            clean = {k: v for k, v in entry.items() if k in allowed}
            receipts.append(dict(pointer='/entries/' + str(i), entry=clean))
    matching = [x for x in receipts if x['entry'].get('sha256') == sha(data)]
    assert matching and all(x['entry']['bytes'] == len(data) for x in matching)
    add('sources/' + name, data, 'questions/' + OLD.name + '/' + rel,
        transport='matching inherited HTTP receipt; not current retrieval',
        source_urls=sorted({x['entry']['url'] for x in matching}))
    receipt_records.append(dict(file=name, receipts=receipts))

nh = '6f893c348e2297eb7bac49bf61c0cb6ab0dd3fcd512eb90124f7715a9fc77287'
add('sources/GSE118660_Tg_3t3s_rsem.genes.expected_count.txt.gz', blob(nh),
    'asset_53dd40f9b97a2571a2fb2632ea636cab', transport='inherited bio-fetch receipt')
fetch_path = OLD / 'inputs/context-audit/NIH-counts-fetch.json'
fetch = json.loads(fetch_path.read_text())
assert fetch['blob'] == nh and fetch['bytes'] == len(blob(nh))
add('provenance/NIH-counts-fetch.json', fetch_path.read_bytes(), 'questions/' + OLD.name + '/inputs/context-audit/NIH-counts-fetch.json')

# Preserve the workbook, proving its archive-member identity without executing formulas.
xlsx_path = OLD / 'inputs/iteration/Gonen-TableS5-native.xlsx'
xlsx = xlsx_path.read_bytes()
parent_path = OLD / 'inputs/iteration/Gonen-supplements.zip'
with zipfile.ZipFile(parent_path) as parent:
    matches = [n for n in parent.namelist() if n.endswith('.xlsx') and parent.read(n) == xlsx]
assert len(matches) == 1
parent_hash = sha(parent_path.read_bytes())
parent_receipts = []
for i, entry in enumerate(transport['entries']):
    if entry.get('sha256') == parent_hash:
        parent_receipts.append(dict(pointer='/entries/' + str(i), entry={k: v for k, v in entry.items() if k in allowed}))
assert parent_receipts
receipt_records.append(dict(file='Gonen-supplements.zip', receipts=parent_receipts))
add('sources/Gonen-TableS5-native.xlsx', xlsx, 'questions/' + OLD.name + '/inputs/iteration/Gonen-TableS5-native.xlsx',
    archive_parent_sha256=parent_hash, archive_member=matches[0], archive_byte_identity=True,
    transport='extracted from inherited supplementary ZIP; not a standalone workbook HTTP receipt')
receipt_excerpt = dict(parent='questions/' + OLD.name + '/inputs/iteration/transport.json',
                      parent_sha256=sha(transport_path.read_bytes()), entries=receipt_records,
                      scope='Selected inherited receipts only; headers/session material excluded; no current HTTP requests.')
(OUT / 'source-receipts.redacted.json').write_bytes(enc(receipt_excerpt))
add('provenance/source-receipts.redacted.json', enc(receipt_excerpt), 'selected inherited receipt excerpts')

artifacts = []
for path in sorted((Q / 'inputs').glob('artifact_*.stdout.json')):
    d = json.loads(path.read_text())
    aid, m = d['id'], d['manifest']
    assert re.fullmatch(r'artifact_[0-9a-f]{64}', aid)
    output_name = 'original-results/' + aid + '/' + m['output']['name']
    add(output_name, blob(m['output']['blob']), aid, historical_output=True)
    add('provenance/' + aid + '.json', path.read_bytes(), 'current catalog readback of unchanged inherited artifact')
    code_members = []
    for h in m['derivation']['code']:
        name = 'original-code/' + h + '.py'
        if name not in MEMBERS:
            add(name, blob(h), aid, execution_policy='evidence only; not executed')
        code_members.append(name)
    for inp in m['derivation']['inputs']:
        blob(inp['blob'])
    artifacts.append(dict(artifact=aid, title=m['title'], output_member=output_name,
                          output_sha256=m['output']['blob'], original_code_members=code_members,
                          original_command=m['derivation']['command'],
                          input_blobs=[v['blob'] for v in m['derivation']['inputs']]))
assert len(artifacts) == 5

# Existing outputs and historical logs are copied unchanged, not reproduced.
original_paths = ['outputs/iteration/isr-summary.json', 'outputs/iteration/isr-samples.tsv',
                  'outputs/iteration/footprint-pmp22-counts.tsv', 'outputs/iteration/footprint-pmp22-TPM.tsv',
                  'outputs/context-audit/counts-primary-source.tsv', 'outputs/context-audit/genotype-controls.tsv',
                  'outputs/iteration/isr-log.txt', 'outputs/iteration/isr-stderr.txt',
                  'outputs/iteration/validation-log.txt', 'outputs/iteration/validation-stderr.txt',
                  'outputs/iteration/followup-log.txt', 'outputs/iteration/followup-stderr.txt',
                  'outputs/context-audit/analysis-r001.log', 'outputs/context-audit/analysis-r001.stderr',
                  'outputs/context-audit/counts.log', 'outputs/context-audit/counts.stderr']
for rel in original_paths:
    add('inherited/' + rel, (OLD / rel).read_bytes(), 'questions/' + OLD.name + '/' + rel,
        provenance='historical bytes, not a new execution receipt')


def soft_records(name):
    data = (OLD / 'inputs/iteration' / name).read_text()
    records = []
    for block in data.split('^SAMPLE = ')[1:]:
        fields = {}
        for line in block.splitlines()[1:]:
            if line.startswith('!Sample_') and ' = ' in line:
                k, v = line.split(' = ', 1)
                fields.setdefault(k.removeprefix('!Sample_'), []).append(v)
        records.append((block.splitlines()[0], fields))
    return records


def header(data, delimiter):
    with gzip.open(io.BytesIO(data), 'rt') as stream:
        return next(csv.reader(stream, delimiter=delimiter))[1:]


mef_columns = header(MEMBERS['sources/GSE118660_MEF-tpm.txt.gz'], '\t')
nih_columns = header(MEMBERS['sources/GSE118660_3t3-TPM.txt.gz'], '\t')
assert mef_columns == header(MEMBERS['sources/GSE118660_MEF-counts.txt.gz'], '\t')
assert nih_columns == header(blob(nh), '\t')
footprint = []
for gsm, fields in soft_records('GSE118660-samples.soft'):
    chars = dict(v.split(': ', 1) for v in fields['characteristics_ch1'])
    assert any('Ribosome footprint profiling data' in s for s in fields['data_processing'])
    if chars['cell line'] == 'MEF':
        genotype = {'WT': 'WT', 'PERK -/-': 'KO'}[chars['genotype']]
        column = 'PERK_' + genotype + '_' + chars['treatment']
        assert column in mef_columns
    else:
        assert chars['cell line'] == 'NIH 3T3'
        column = 'NIH3T3_' + ('Cont' if chars['treatment'] == 'Control' else chars['treatment'])
        assert column in nih_columns
    footprint.append(dict(gsm=gsm, native_column=column, title=fields['title'][0],
                          source_characteristics=fields['characteristics_ch1'],
                          source_description=fields['description'],
                          source_library_strategy=fields['library_strategy'],
                          source_molecule=fields['molecule_ch1'], assay='ribosome footprints per explicit source processing'))
assert {x['native_column'] for x in footprint} == set(mef_columns + nih_columns)
assert len(footprint) == len(mef_columns) + len(nih_columns) == 13
isr_source = dict(soft_records('GSE90070-samples.soft'))
isr_map = list(csv.DictReader(io.StringIO((OLD / 'outputs/iteration/isr-samples.tsv').read_text()), delimiter='\t'))
isr_columns = header(MEMBERS['sources/GSE90070_dataCount.csv.gz'], ',')
assert [r[''] for r in isr_map] == isr_columns and len(isr_map) == len(isr_source) == 32
pairs = {}
for row in isr_map:
    fields = isr_source[row['gsm']]
    assert fields['title'] == [row['title']]
    assert 'Sample name: ' + row[''] in fields['description']
    assert row['title'] == '_'.join([row['condition'], row['fraction'], row['replicate']])
    pairs.setdefault(row['pair'], {})[row['fraction']] = dict(column=row[''], gsm=row['gsm'])
assert len(pairs) == 16 and all(set(v) == {'In', 'H'} for v in pairs.values())
design = (OLD / 'inputs/iteration/GSE90070.soft').read_text()
assert 'RNA of every sample was seperated into Input' in design
locators = dict(scope='New structural locator extraction only; no effect estimation or normalization',
                GSE118660=footprint, GSE90070_pairs=pairs,
                GSE90070_original_map='inherited/outputs/iteration/isr-samples.tsv',
                mapping_rules='Literal native columns checked against GEO cell-line/genotype/treatment fields; KO maps explicit PERK -/- and NIH Cont maps explicit Control. No sample identities inferred across studies.',
                pairing_limit='Fraction pairing within source condition/replicate only; no cross-treatment pairing or verified independent donors.')
(OUT / 'sample-locators.json').write_bytes(enc(locators))
add('sample-locators.json', enc(locators), 'current header and native metadata checks')

calibration = dict(
    GSE118660=dict(primary='PMC6416471; PMID30867432; Methods: Ribosome footprint profiling',
                  units='RSEM expected counts (possibly fractional) and TPM, not raw integer read counts or an RNA denominator.',
                  matched_RNA_RPF='No separate matched RNA denominator identified in these 13 footprint libraries.',
                  absolute_scale='Source Methods explicitly states relative, not absolute protein synthesis. No verified per-library external spike/global-synthesis factors supplied in this handoff.',
                  time_conflict='NIH3T3 late 7h in GEO/Methods versus 8h in Table S5B; unchanged source labels retained.'),
    GSE90070=dict(primary='PMC5730339; PMID29220654; series overall_design; Methods Protein synthesis / Polysome profiling',
                 units='Deposited read counts for cytosolic and heavy-polysome-associated RNA (>4 ribosomes), not RPF counts.',
                 pairing='16 source-design-supported In/H pairs; 4 labelled replicate pairs in each of 4 conditions.',
                 global_assay='Paper describes 30-minute [35S]Met/Cys incorporation into total cellular protein, plus a separate ribosome half-transit assay.',
                 calibration_limit='These study-level assays are not verified per-library spike factors, an absolute PMP22 synthesis rate, or a cross-study RNA/RPF pairing. No such calibration table was located among the reviewed original outputs.'),
    peer_correction=dict(artifact='artifact_882bd250c232e55f8c377e3c895353fe414351297a3fbd9b76a4483d8874f486',
                         disputed='Total RNA-seq only in audited design',
                         correction='For GSE118660 this generic-label reading is contradicted by explicit footprint processing in native SOFT and PMC6416471. Retain the no-valid-RNA/RPF-join limitation, not the RNA-only assay classification.'))
manifest = dict(question=Q.name, source_question=OLD.name,
                request='post_08ad94d4992e46d5af511bf946a6700c', files=FILES,
                original_artifacts=artifacts, sample_metadata=locators, pairing_and_calibration=calibration,
                provenance_limits='Original manifest command arrays retained as found; historical logs are not reconstructed producer receipts. Original artifact publication retains broader original dependencies (including ancillary validation/TE/granule inputs); this ZIP is restricted to the requested footprint/fraction sources and small provenance outputs.',
                execution_scope='Byte-preserving export and source-metadata/header checks only. No scientific rerun, source HTTP requests, raw processing, inherited-code execution or workbook formula execution.')
manifest_data = enc(manifest)
(OUT / 'source-locator-manifest.json').write_bytes(manifest_data)
MEMBERS['source-locator-manifest.json'] = manifest_data
archive_path = OUT / 'stress-source-evidence.zip'
with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(MEMBERS.items()):
        archive.writestr(name, data)
with zipfile.ZipFile(archive_path) as archive:
    assert set(archive.namelist()) == set(MEMBERS)
    for name, data in MEMBERS.items():
        assert archive.read(name) == data
verification = dict(valid=True, archive_sha256=sha(archive_path.read_bytes()),
                    archive_bytes=archive_path.stat().st_size, archive_members=len(MEMBERS),
                    original_artifacts=len(artifacts), footprint_libraries=len(footprint),
                    fraction_libraries=len(isr_map), fraction_pairs=len(pairs),
                    workbook_parent_identity=True, scientific_rerun=False,
                    original_commands=[x['original_command'] for x in artifacts])
(OUT / 'byte-verification.json').write_bytes(enc(verification))
print(json.dumps(verification, indent=2))
