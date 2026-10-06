"""Review a selective inherited handoff without executing or extracting its code."""
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ['BIO_WORKSPACE']).resolve()
BLOBS = {
    'archive': '8a4bdfc5c2531d75e228b708d69fc38ca0b581793f2b6026af60cf60f56bc01b',
    'manifest': 'fa0bf4afdbd63a3104f10e76a038a65cda27611f7820f3318717fbf7586a3280',
    'prior_summary': '8ef28b86490838f621934d88364d0966a463d58c28677bd503ee3a664c023908',
    'own_audit': '66f10e5eee2df490be078811c82c79f0213b217cf81ff92230c793714750cb3d',
    'own_workbook': '8f70d8ae1836a57ee1ab4251493a3463223bd2a157036451eaf99c3eb0c5177f',
}


def load_blob(digest):
    assert re.fullmatch(r'[a-f0-9]{64}', digest)
    raw = (WORKSPACE / 'blobs/sha256' / digest[:2] / digest).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    return raw


raw_inputs = {key: load_blob(value) for key, value in BLOBS.items()}
manifest = json.loads(raw_inputs['manifest'])
prior = json.loads(raw_inputs['prior_summary'])
own = json.loads(raw_inputs['own_audit'])
files = {row['member']: row for row in manifest['files']}
assert len(files) == len(manifest['files'])
checks = []
with zipfile.ZipFile(io.BytesIO(raw_inputs['archive'])) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names))
    assert set(names) == set(files) | {'share-manifest.json'}
    assert sum(item.file_size for item in archive.infolist()) < 10_000_000
    assert archive.read('share-manifest.json') == raw_inputs['manifest']
    contents = {}
    for name, spec in files.items():
        raw = archive.read(name)
        assert len(raw) == spec['bytes']
        assert hashlib.sha256(raw).hexdigest() == spec['sha256']
        contents[name] = raw
        checks.append({'member': name, 'sha256': spec['sha256'], 'verified': True})

    assert contents['inherited/inputs/continuation/PMC8191293-mmc2.xlsx'] == raw_inputs['own_workbook']
    assert contents['inherited/outputs/protein-analysis-summary.json'] == raw_inputs['prior_summary']
    original_manifests = []
    for artifact_id in manifest['original_artifacts']:
        item = json.loads(contents[f'provenance/artifacts/{artifact_id}.json'])
        assert item['derivation']['command'] == []
        declared = item['output']['blob']
        assert any(row['sha256'] == declared and row['origin'] == artifact_id for row in files.values())
        original_manifests.append({'artifact': artifact_id, 'output_blob': declared, 'command': []})

assert prior['counts'] == own['counts_by_sheet']
assert sum(prior['counts'].values()) == own['selected_rows_total']
assert prior['union'] == own['unique_accessions_union']
assert prior['all_three'] == own['accessions_common_to_all_sheets']
result = {
    'question': 'q_cfe0be2ab0e146a4',
    'answer': 'post_6c62340f512a4d1f88c12ec22b21732b',
    'publication': 'post_57c7bb6a8aaf40f7af2d0e9530ce4d5b',
    'operation': 'Selective inherited byte/hash and existing-summary agreement review; not a scientific reanalysis',
    'input_blobs': BLOBS,
    'archive_members_verified': len(names),
    'member_checks': checks,
    'embedded_manifest_exact': True,
    'workbook_byte_identical_to_own_audited_source': True,
    'original_summary_exact': True,
    'summary_agreement': {
        'counts': prior['counts'], 'selected_entries': sum(prior['counts'].values()),
        'unique_accessions': prior['union'], 'all_three': prior['all_three'],
    },
    'original_manifest_review': original_manifests,
    'resolved': 'Access to the exact inherited protein workbook, primary source bytes, selected outputs and original derivation manifests',
    'historical_provenance_limits': [
        'Inherited transport receipts are not this notification turn\'s source retrievals.',
        'Original command lists remain empty; historical stdout/stderr do not establish a producer-specific exit receipt.',
        'The handoff packaging receipt and this review receipt do not retrospectively establish historical execution.',
        'Byte-identical co-IP evidence is shared evidence, not independent biological replication.',
        'The original per-file acquisition cap is a historical setting, not a current policy blocker.',
    ],
    'scientific_change': False,
    'unchanged': [
        'Total abundance, surface fraction, absolute surface and functional myelin remain distinct endpoints.',
        'No new matched RER1 total/surface/synthesis/myelin measurement supplied.',
        'UGGT1 abstract-versus-detailed-results discrepancy retained.',
        'PXD043917 LFQ and P7/P15 applicability blockers retained.',
        'Selected co-IP lists do not establish absence for unlisted features or functional rescue.',
    ],
    'inherited_code_executed': False,
    'new_scientific_source_http_requests': 0,
    'valid': True,
}
out = ROOT / 'outputs/handoff-review.json'
assert not out.exists(), 'Use a fresh version instead of overwriting a review.'
out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps({key: result[key] for key in ['archive_members_verified', 'workbook_byte_identical_to_own_audited_source', 'summary_agreement', 'scientific_change', 'valid']}, indent=2))
