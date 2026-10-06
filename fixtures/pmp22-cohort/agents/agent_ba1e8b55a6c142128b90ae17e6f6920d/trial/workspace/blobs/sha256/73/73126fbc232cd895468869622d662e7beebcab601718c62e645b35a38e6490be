"""Validate source-located, agent-curated eligibility; export a reusable evidence audit.

This script performs no new biological experiment, image digitization, matrix
imputation or imported-code execution. Source statements and interpretations are
kept separate. Missing measurements and unknown units stay explicit.
"""
import csv
import hashlib
import json
import platform
from pathlib import Path

from defusedxml import ElementTree as ET

Q = Path(__file__).resolve().parents[1]
INPUTS = Q / 'inputs'
OUTPUTS = Q / 'outputs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def norm(s):
    return ' '.join(s.split())


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    assert load(path) == obj


curation = load(INPUTS / 'endpoint-curation.json')
design = load(INPUTS / 'bidirectionality-design-curation.json')
reuse = load(INPUTS / 'reuse-provenance.json')
assert design['status'] == 'proposed_not_performed'
for r in reuse['inherited_inputs']:
    assert sha(INPUTS / r['name']) == r['sha256'], r['name']

records = curation['records']
assert len({r['id'] for r in records}) == len(records)
checks = []
for r in records:
    p = INPUTS / r['source']
    if p.suffix == '.xml':
        root = ET.fromstring(p.read_bytes())
        assert root.tag == 'article', (p, root.tag)
        text = norm(' '.join(root.itertext()))
        ids = {e.get('pub-id-type'): e.text for e in root.findall('.//article-id')}
    else:
        doc = load(p)
        hits = [x for x in doc['resultList']['result'] if x.get('pmid') == r['pmid']]
        assert len(hits) == 1
        text = norm(hits[0]['abstractText'])
        ids = {k: hits[0].get(k) for k in ('pmid', 'pmcid', 'doi')}
    assert norm(r['anchor']) in text, (r['id'], r['anchor'])
    assert r['biological_unit'] and r['selection'] and r['not_identified']
    assert r['unit_count'] is None or (isinstance(r['unit_count'], int) and r['unit_count'] > 0)
    r['source_sha256'] = sha(p)
    r['article_ids'] = ids
    r['eligible_endogenous_promoter_nascent_test'] = False
    r['assessment_type'] = 'agent_curated_from_source_not_new_experimental_result'
    checks.append({'record': r['id'], 'anchor_verified': True, 'source_sha256': sha(p)})

# Verify exact contextual guardrails beyond the individual claim anchors.
f = norm(' '.join(ET.parse(INPUTS / 'PMC13042600.xml').getroot().itertext()))
for anchor in ['Dhh Cre', '5–6 days old', 'GSE216665', 'reasonable request']:
    assert anchor in f, anchor
lxr = norm(' '.join(ET.parse(INPUTS / 'PMC5802790.xml').getroot().itertext()))
for anchor in ['from P21 to P56', 'bringing it even lower than in WT', 'selective siRNA']:
    assert anchor in lxr, anchor
lpa = norm(' '.join(ET.parse(INPUTS / 'PMC3315401.xml').getroot().itertext()))
for anchor in ['male Sprague-Dawley rats', 'n = 5 per group', '19 kDa band for PMP22']:
    assert anchor in lpa, anchor

# Preserve real transport evidence, detecting false success from content/status.
retrievals = []
for p in sorted(INPUTS.glob('*.receipt.json')):
    rec = load(p)
    target = INPUTS / rec['name']
    if 'sha256' in rec:
        assert sha(target) == rec['sha256']
        assert target.stat().st_size == rec['bytes']
    text = target.read_text(errors='replace') if target.exists() else ''
    if rec.get('status') != 200:
        state = 'http_or_transport_failure'
    elif 'recaptcha/challengepage' in text or '<title>Client Challenge</title>' in text:
        state = 'challenge_not_source'
    elif text.startswith('[Error] : No result can be found'):
        state = 'no_result_not_source'
    elif target.suffix == '.json':
        data = load(target)
        state = 'valid_search_result' if 'resultList' in data else 'unclassified_json'
    elif target.suffix == '.xml':
        assert ET.fromstring(target.read_bytes()).tag == 'article'
        state = 'valid_primary_article'
    else:
        state = 'unclassified_html_not_used_as_evidence'
    retrievals.append(dict(rec, validation=state, receipt_sha256=sha(p)))

searches = []
for name in ['progesterone-mechanism-search.json', 'progesterone-focused.json', 'lipid-primary-abstracts.json']:
    data = load(INPUTS / name)
    n = len(data['resultList']['result'])
    searches.append({'source': name, 'query': data['request']['queryString'], 'hitCount': data['hitCount'],
                     'returned': n, 'truncated': n < data['hitCount']})

inputs = [{'path': str(p.relative_to(Q)), 'sha256': sha(p), 'bytes': p.stat().st_size}
          for p in sorted(INPUTS.iterdir()) if p.is_file()]
manifest = {'question': curation['question'], 'inputs': inputs, 'current_http_retrievals': retrievals,
            'inherited_provenance': reuse, 'search_coverage': searches,
            'source_locators': [{'id': r['id'], 'source': r['source'], 'sha256': r['source_sha256'],
                                 'article_ids': r['article_ids'], 'locator': r['locator'],
                                 'anchor': r['anchor'], 'source_type': r['source_type']} for r in records]}
audit = {'question': curation['question'], 'scope': curation['type'], 'records': records,
         'primary_identifiability_result': 'No audited contrast supplies the full matched endogenous promoter-nascent, RNA-fate and absolute productive-protein-delivery measurements. This is bounded eligibility, not global absence of such data.',
         'starting_position_revision': 'Both gene-regulatory and protein-environment branches have source support. Their relative mediation cannot be ranked from unmatched endpoints. PMP22-to-lipid direction has genetic support; a closed transcriptional feedback loop remains unproven.',
         'verified_measurement_gap': 'PMC5802790 P21/adult/NAC comparison reports total protein, redox and tissue function but does not supply matched P1/P2 nascent output or RNA/turnover decomposition. Preventive recovery is not delayed rescue or exact normalization of anatomy.',
         'FDFT1_blocker': 'Article/source-request prerequisite verified; historical supplement-inventory claim remains inherited. GSE216665 is a different rat injury study, not an eligible substitute for the mouse Fdft1 genotype matrix.',
         'reuse': reuse['considered_and_reused'], 'search_coverage': searches,
         'limitations': ['Agent-curated source audit, not independent replication or novel regulator discovery.',
                         'Abstract-only records lack full methods and exact units; all such fields remain unknown.',
                         'Reported summaries were not digitized or treated as individual measurements.',
                         'Retinoid/metabolic branches beyond the chosen contrast are deferred, not disproven.',
                         'Inherited locked failures and unsupported-browser retractions remain in LABBOOK.']}
dump(OUTPUTS / 'endpoint-audit.json', audit)
dump(OUTPUTS / 'source-manifest.json', manifest)
dump(OUTPUTS / 'bidirectionality-design.json', design)
fields = ['id', 'source', 'source_type', 'source_sha256', 'locator', 'species', 'age', 'sex', 'genotype_driver',
          'compartment', 'contrast', 'exposure_time', 'biological_unit', 'unit_count', 'assays',
          'PMP22_mature_RNA', 'PMP22_promoter_nascent', 'PMP22_total_protein', 'PMP22_absolute_surface',
          'lipid_or_function', 'eligible_for', 'not_identified', 'selection', 'observed']
with (OUTPUTS / 'assay-eligibility.tsv').open('w', newline='') as stream:
    writer = csv.DictWriter(stream, fields, delimiter='\t')
    writer.writeheader()
    for r in records:
        row = {k: r[k] for k in fields}
        row['assays'] = '; '.join(row['assays'])
        row['unit_count'] = 'unknown' if row['unit_count'] is None else row['unit_count']
        writer.writerow(row)
with (OUTPUTS / 'assay-eligibility.tsv').open(newline='') as stream:
    reread = list(csv.DictReader(stream, delimiter='\t'))
assert len(reread) == len(records)
assert [r['id'] for r in reread] == [r['id'] for r in records]
summary = {'records': len(records), 'source_anchor_checks': len(checks),
           'inputs_hashed': len(inputs), 'current_HTTP_attempts': len(retrievals),
           'proposed_decision_cases': len(design['decisions']), 'finite_JSON_roundtrips': True,
           'TSV_row_roundtrip': True, 'biological_reanalysis': False,
           'producer_sha256': sha(Path(__file__)), 'python': platform.python_version(),
           'checks': checks,
           'outputs': {n: sha(OUTPUTS / n) for n in ['endpoint-audit.json', 'source-manifest.json',
                                             'bidirectionality-design.json', 'assay-eligibility.tsv']}}
dump(OUTPUTS / 'validation.json', summary)
print(json.dumps({k: v for k, v in summary.items() if k not in ['checks', 'outputs']}, allow_nan=False))
