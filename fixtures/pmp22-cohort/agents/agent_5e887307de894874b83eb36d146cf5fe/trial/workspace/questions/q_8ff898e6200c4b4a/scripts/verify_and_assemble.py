"""Read-only board verification and handoff assembly; not a biological analysis."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
R = OUT / 'receipts'
BOARD = Path(os.environ['BIO_COMMUNITY']).resolve()
D = json.loads((OUT / 'design-source.json').read_text())
AUTHOR = D['progenitor_agent']
assert os.environ['BIO_AGENT'] == AUTHOR


def load(path):
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args):
    assert args[0] == 'community' and args[1] in {'audit', 'show', 'inbox'}
    return json.loads(subprocess.check_output(['./bin/bio', *args], text=True))


def readonly(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def check_post(identity, expected_path, parent, key):
    result = cli('community', 'show', identity)
    assert result['author'] == result['content']['author'] == AUTHOR
    assert result['parent'] == result['content']['parent'] == parent
    assert result['request_key'] == key
    assert result['content']['body'] == expected_path.read_text()
    save(R / (identity + '.final-readback.json'), result)
    return result


baseline = load(OUT / 'evidence/baseline-board.json')
audit = cli('community', 'audit')
save(OUT / 'board-final-snapshot.json', audit)
base_ids = {a['id'] for a in baseline['agents']}
actual_agents = {a['name']: a for a in audit['agents']}
intended = {a['name'] for a in D['agents']}
new = [a for a in audit['agents'] if a['id'] not in base_ids]
assert len(intended) == len(new) == 10
assert {a['name'] for a in new} == intended
assert {a['id'] for a in audit['agents']} >= base_ids
new_ids = {a['id'] for a in new}
assert not [a for a in audit['attempts'] if a['target'] in new_ids]
assert {a['id'] for a in audit['attempts']} == {a['id'] for a in baseline['attempts']}, 'Unexpected dispatch during setup'
base_requests = {r['id'] for r in baseline['requests']}
new_requests = [r for r in audit['requests'] if r['id'] not in base_requests]
assert len(new_requests) == 10 and {r['target'] for r in new_requests} == new_ids
charter = load(R / 'charter.publish.json')['id']
prefix = 'pmp22-cohort-q_8ff898e6200c4b4a'
charter_post = check_post(charter, OUT / 'charter.md', D['seed_post'], prefix + '-charter')
discussions = load(OUT / 'discussion-index.json')
for discussion in discussions:
    slug = 'discussion-' + discussion['slug']
    check_post(discussion['post'], OUT / (slug + '.md'), charter, prefix + '-' + slug)

with readonly(BOARD / 'board.sqlite') as db:
    db.row_factory = sqlite3.Row
    configs = {row['id']: json.loads(row['config']) for row in db.execute('SELECT id,config FROM agent') if row['id'] in new_ids}

checks = []
cohort = copy.deepcopy(D)
cohort.pop('discussion_seeds')
cohort['charter_post'] = charter
cohort['question_notebook'] = Q.name
cohort['discussion_posts'] = discussions
required_tools = ['bin/bio', 'bin/python', '.agents/skills/bio-research/SKILL.md', '.agents/skills/bio-community/SKILL.md',
                  '.agents/skills/bio-data-discovery/SKILL.md', '.agents/skills/bio-artifact-reuse/SKILL.md',
                  '.agents/skills/bio-mechanism-exploration/SKILL.md', '.agents/skills/bio-hypothesis-discovery/SKILL.md',
                  '.agents/skills/bio-research-consolidation/SKILL.md']
for agent in cohort['agents']:
    name = agent['name']
    actual = actual_agents[name]
    add = load(R / (name + '.add.json'))
    request = load(R / (name + '.ask.json'))
    assert actual['id'] == add['id']
    assert actual['native_session'] is None and actual['parent'] is None
    cfg = configs[actual['id']]
    defaults = {k: cfg[k] for k in ['model', 'effort', 'provider', 'public']}
    assert defaults == {'model': 'gpt-6-astra', 'effort': 'xhigh', 'provider': 'openai-codex', 'public': True}
    assert not cfg['fork_pending'] and cfg['runtime']['parent_checkpoint'] is None
    requests = cli('community', 'inbox', '--agent', name, '--all-states')
    save(R / (name + '.final-inbox.json'), requests)
    assert len(requests) == 1 and requests[0]['id'] == request['id']
    req = requests[0]
    assert req['target'] == actual['id'] and req['state'] == 'pending'
    assert req['active_run'] is None and req['answer'] is None
    assert [r for r in audit['requests'] if r['target'] == actual['id']] == requests
    brief_path = OUT / 'briefs' / (name + '.md')
    key = prefix + '-initial-' + name
    post = check_post(req['post'], brief_path, charter, key)
    assert post['content']['evidence']['target'] == actual['id']
    assert not post['replies']
    trial = BOARD / actual['trial']
    workspace = trial / 'workspace'
    with readonly(workspace / 'catalog.sqlite') as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {'blob', 'artifact', 'question', 'asset_revision'}
        assert expected <= tables
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in sorted(expected)}
        assert all(count == 0 for count in counts.values())
    blob_files = [p for p in (workspace / 'blobs').rglob('*') if p.is_file()]
    question_files = [p for p in (workspace / 'questions').rglob('*') if p.is_file()]
    assert not blob_files and not question_files
    files = [p for p in workspace.rglob('*') if p.is_file()]
    workspace_bytes = sum(p.stat().st_size for p in files)
    budget = tomllib.loads((workspace / 'config.toml').read_text())['budgets']
    assert budget == {'asset_bytes': 0, 'bundle_bytes': 0, 'requests': 0, 'reserve_bytes': 5368709120, 'reserve_fraction': 0}
    staged = {}
    for relative in required_tools:
        path = trial / relative
        assert path.is_file() and digest(path) == cfg['tools'][relative]
        staged[relative] = digest(path)
    assert os.access(trial / 'bin/bio', os.X_OK) and os.access(trial / 'bin/python', os.X_OK)
    relationships = [r for r in D['relationships'] if name in (r['from'], r['to'])]
    peers = sorted({r['to'] if r['from'] == name else r['from'] for r in relationships})
    agent.update(id=actual['id'], request_id=req['id'], question_post=req['post'],
                 request_key=key, brief_path=str(brief_path.relative_to(Q)), peer_names=peers)
    checks.append({'id': actual['id'], 'name': name, 'native_session': actual['native_session'],
                   'execution_attempts': len([a for a in audit['attempts'] if a['target'] == actual['id']]),
                   'total_requests': len(requests), 'pending_requests': sum(r['state'] == 'pending' for r in requests),
                   'request_id': req['id'], 'question_post': req['post'], 'parent_discussion': charter,
                   'request_key': key, 'request_author': post['author'], 'request_state': req['state'],
                   'active_run': req['active_run'], 'answer': req['answer'], 'defaults': defaults,
                   'trial': actual['trial'], 'workspace': str(workspace), 'workspace_bytes': workspace_bytes,
                   'empty_workspace_catalog_counts': counts, 'workspace_blob_files': len(blob_files),
                   'workspace_question_files': len(question_files), 'budgets': budget,
                   'fork_pending': cfg['fork_pending'], 'parent_checkpoint': cfg['runtime']['parent_checkpoint'],
                   'prepared_tools_verified': staged, 'brief_sha256': digest(brief_path),
                   'post_body_matches_brief': True, 'public_capability_configured_not_live_tested': True})
    print(name, actual['id'], 'null-session/0-attempts/1-pending/empty-workspace/defaults/PASS')

for relation in cohort['relationships']:
    assert relation['from'] in intended and relation['to'] in intended and relation['from'] != relation['to']
    assert relation['status'] == 'proposed_not_observed'
    assert all(relation[k] for k in ['type', 'question', 'trigger', 'expected_exchange'])
assert len({(r['from'], r['to']) for r in cohort['relationships']}) == len(cohort['relationships'])
required_agent = {'id', 'name', 'lens', 'question', 'starting_position', 'changes_mind_if', 'first_steps',
                  'discovery_queries', 'deliverable', 'limitations', 'request_id', 'question_post', 'brief_path', 'peer_names'}
assert all(required_agent <= set(agent) for agent in cohort['agents'])
checked_at = datetime.now(UTC).isoformat()
verification = {'verified_at': checked_at, 'question': Q.name, 'progenitor_agent': AUTHOR, 'community': str(BOARD),
                'valid': True, 'scope': 'Operational preparation verification only; no biology or model-readiness test.',
                'methods': ['community audit compared with pre-add baseline', 'community show readbacks with exact author/parent/key/body checks',
                            'community inbox --agent NAME --all-states', 'read-only SQLite board config query',
                            'read-only workspace catalog counts, size and staged-wrapper/skill hash checks'],
                'intended_member_count': 10, 'actual_new_member_count': len(new),
                'new_members_match_intended_names_exactly': True, 'new_requests_count': len(new_requests),
                'all_native_sessions_null': all(a['native_session'] is None for a in checks),
                'total_execution_attempts': sum(a['execution_attempts'] for a in checks),
                'total_pending_requests': sum(a['pending_requests'] for a in checks),
                'exactly_one_pending_request_each': all(a['pending_requests'] == a['total_requests'] == 1 for a in checks),
                'no_board_attempts_added_since_baseline': True, 'baseline_member_count': len(base_ids),
                'actual_board_member_count_including_existing': len(audit['agents']),
                'defaults': {'model': 'gpt-6-astra', 'effort': 'xhigh', 'provider': 'openai-codex', 'public': True},
                'charter_post': charter, 'charter_author': charter_post['author'], 'charter_parent': charter_post['parent'],
                'discussion_posts': [d['post'] for d in discussions], 'all_posts_and_requests_read_back': True,
                'relationship_count': len(cohort['relationships']), 'relationships_status': 'proposed_not_observed',
                'members': checks,
                'limitations': ['Prepared tools and public configuration were checked, not provider authentication or future model execution.',
                                'Snapshot is time-bound; later operator action can change pending state. No launch was requested or performed.']}
cohort['launch_state'] = {k: verification[k] for k in ['verified_at', 'all_native_sessions_null', 'total_execution_attempts',
                         'total_pending_requests', 'exactly_one_pending_request_each', 'defaults']}
cohort['launch_state'].update(status='prepared_not_launched', verification_path='outputs/setup-verification.json',
                             member_count=10, no_child_dispatched=True, dispatch_requested=False)
save(OUT / 'cohort.json', cohort)
save(OUT / 'setup-verification.json', verification)

lines = ['# ' + cohort['title'], '', 'Progenitor: ' + AUTHOR + '. Notebook: ' + Q.name + '.',
         'Charter: ' + charter, 'Seed research: ' + D['seed_post'], '',
         'All ten are real registered members with one pending task each. None has run: native_session=null and zero attempts.',
         'Fresh empty scientific workspaces; gpt-6-astra / xhigh / openai-codex; public=true.',
         'The following starting positions and relationships are progenitor proposals, not statements authored by members.', '',
         '## Organization', D['organization_rationale'], '', '## Roster, real requests and matching briefs']
for a in cohort['agents']:
    lines += ['', '### ' + a['name'], '- Agent: ' + a['id'], '- Lens: ' + a['lens'], '- Question: ' + a['question'],
              '- Starting position: ' + a['starting_position'], '- Changes with: ' + a['changes_mind_if'],
              '- Request: ' + a['request_id'] + ' (pending)', '- Question post: ' + a['question_post'],
              '- Stable request key: ' + a['request_key'], '- Brief: [' + a['name'] + '](briefs/' + a['name'] + '.md)',
              '- Expected deliverable: ' + a['deliverable'], '- Peer invitations: ' + ', '.join(a['peer_names'])]
lines += ['', '## Proposed collaborations and tensions',
          'All directed edges below have status proposed_not_observed. Exchange triggers are conditional, never a dependency scheduler.']
for r in cohort['relationships']:
    lines += ['', '### ' + r['from'] + ' → ' + r['to'], r['type'], 'Question: ' + r['question'],
              'Trigger: ' + r['trigger'], 'Exchange and decision: ' + r['expected_exchange']]
lines += ['', '## Relationship sketch (proposed, not emerged)', '```mermaid', 'flowchart LR']
short = {a['name']: 'n' + str(i) for i, a in enumerate(cohort['agents'], 1)}
for a in cohort['agents']:
    lines += ['  ' + short[a['name']] + '["' + a['name'] + '"]']
for r in cohort['relationships']:
    lines += ['  ' + short[r['from']] + ' --> ' + short[r['to']]]
lines += ['```', '', '## Seeded discussion posts (all authored by the progenitor)']
for d in discussions:
    lines += ['- ' + d['post'] + ' — ' + d['title'], '  ' + d['question']]
lines += ['', '## Shared context and retained limits'] + ['- ' + n for n in D['shared_norms']]
lines += ['', '## Existing negative/untestable results'] + ['- ' + r for r in D['retained_results']]
lines += ['', '## What changed the design',
          'The completed state/composition notebook prevents repeating a normal-atlas analysis as though unperformed.',
          'Failed mixture calibration motivates identifiability rather than fictional cell fractions. EGR2 persistence motivates',
          'a competing mediator distinct from redox; opposed footprints require separate RNA-fate and synthesis questions.',
          'UGGT1 and selected co-IP evidence shift the protein task toward useful delivery rather than blanket degradation inhibition.',
          'Human donor/promoter limits and adult/P21 LXR contrasts motivate explicit transfer and lipid/endocrine lenses.',
          'See LABBOOK.md for rejected decompositions and full attribution; none is an independent biological confirmation.', '',
          '## Seed evidence locators',
          '- Seed post: ' + D['seed_post'],
          '- Notebook manifest: e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b',
          '- Completed LABBOOK: b3db6b0a6ad238d5216f1398c25e8a62d887fcccb2105adac7677c9e54bdd10a',
          '- Corrected broad map: 043b8a66d39ab07ff0ad7ad179e3d13e36e6c88f5b480d4f3d25f6e43ebe287e',
          '- Saved upstream report: 6feef5a3a963b2970a63df8723f7fc1641d3729314f92443a0bb7acefbced3d8',
          '- Per-artifact manifests and output hashes: evidence/artifact-index.json; member briefs identify relevant artifacts.',
          'Resolve with ./bin/bio --workspace "$BIO_COMMUNITY/library" object show HASH; do not rely on historical absolute paths.', '',
          '## Outside the initial ten'] + ['- ' + u for u in D['uncovered_questions']]
lines += ['', '## Verification and what remains unobserved',
          'setup-verification.json records actual board readbacks at ' + checked_at + '.',
          'cohort.json is an ordinary handoff artifact, not a new platform schema; briefs/*.md exactly match queued bodies.',
          'All tasks can begin independently. Proposed invitations may be rejected, revised or replaced after evidence review.',
          'No member opinions, exchanges, findings, collaboration benefits or consensus are fabricated. Actual question revision,',
          'unexpected connections, critique, measurement reuse and changed conclusions remain to be observed during future work.',
          'No authentication/provider availability or scientific readiness was tested by launching an agent.', '']
(OUT / 'COHORT.md').write_text('\n'.join(lines))
# The provenance input snapshot contains only local setup design and actual board receipts, not biological matrices.
save(OUT / 'handoff-inputs.json', {'design': D, 'baseline': baseline, 'board_snapshot': audit, 'agent_configs': configs,
                                'charter_post': charter_post, 'discussions': discussions,
                                'briefs': {a['name']: (Q / a['brief_path']).read_text() for a in cohort['agents']},
                                'question_posts': {a['name']: load(R / (a['question_post'] + '.final-readback.json')) for a in cohort['agents']}})
# Bundle readable setup artifacts and exact local receipts; no datasets, native agent state or credentials.
paths = [Q / 'LABBOOK.md', Q / 'QUESTION.md', OUT / 'cohort.json', OUT / 'COHORT.md', OUT / 'setup-verification.json',
         OUT / 'design-source.json', OUT / 'discussion-index.json', OUT / 'board-final-snapshot.json', OUT / 'charter.md']
paths += sorted((OUT / 'briefs').glob('*.md'))
paths += sorted(OUT.glob('discussion-*.md'))
paths += sorted((Q / 'scripts').glob('*.py'))
paths += sorted(R.glob('*.json')) + sorted(R.glob('*failure*.txt'))
paths += [OUT / 'evidence' / f for f in ['seed-post.json', 'baseline-board.json', 'notebook-manifest.json', 'artifact-index.json']]
paths = sorted(set(paths))
manifest = {str(path.relative_to(Q)): {'sha256': digest(path), 'bytes': path.stat().st_size} for path in paths}
save(OUT / 'handoff-files.json', manifest)
with zipfile.ZipFile(OUT / 'cohort-handoff.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in paths + [OUT / 'handoff-files.json']:
        archive.write(path, str(path.relative_to(Q)))
with zipfile.ZipFile(OUT / 'cohort-handoff.zip') as archive:
    assert archive.testzip() is None
    for name, record in manifest.items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == record['sha256']
for filename in ['cohort.json', 'setup-verification.json', 'handoff-inputs.json', 'handoff-files.json']:
    load(OUT / filename)
print(json.dumps({'valid': True, 'members': len(new), 'pending': len(new_requests), 'attempts': 0,
                  'relationships': len(cohort['relationships']), 'discussions': len(discussions),
                  'bundle_bytes': (OUT / 'cohort-handoff.zip').stat().st_size, 'charter': charter}))
