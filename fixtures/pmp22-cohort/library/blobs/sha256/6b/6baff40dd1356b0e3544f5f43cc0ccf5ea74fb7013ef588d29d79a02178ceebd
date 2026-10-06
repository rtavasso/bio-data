"""Supported preparation operations only. No model invocation or dispatch is implemented."""
import argparse
import json
import os
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
RECEIPTS = OUT / 'receipts'
RECEIPTS.mkdir(exist_ok=True)
DESIGN = json.loads((OUT / 'design-source.json').read_text())
AUTHOR = DESIGN['progenitor_agent']
PREFIX = 'pmp22-cohort-q_8ff898e6200c4b4a'
assert os.environ['BIO_AGENT'] == AUTHOR
assert Path(os.environ['BIO_WORKSPACE']).resolve() == Q.parents[1]
assert len(DESIGN['agents']) == len({a['name'] for a in DESIGN['agents']}) == 10
ALLOWED = {'add-agent', 'agents', 'publish', 'show', 'ask', 'inbox', 'audit'}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def call(action, *args, receipt=None):
    assert action in ALLOWED
    command = ['./bin/bio', 'community', action, *map(str, args)]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if receipt:
        receipt.with_suffix('.stdout.json').write_text(result.stdout)
        receipt.with_suffix('.stderr.txt').write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f'{action} failed ({result.returncode}): {result.stderr}')
    value = json.loads(result.stdout)
    if receipt:
        save(receipt, value)
    return value


def read(name):
    return json.loads((RECEIPTS / name).read_text())


def roster():
    return [read(a['name'] + '.add.json') for a in DESIGN['agents']]


def verify_post(post_id, body, parent, key):
    got = call('show', post_id, receipt=RECEIPTS / (post_id + '.readback.json'))
    assert got['author'] == AUTHOR and got['content']['author'] == AUTHOR
    assert got['parent'] == parent and got['content']['parent'] == parent
    assert got['request_key'] == key and got['content']['body'] == body
    return got


def publish(slug, title, body, parent, notebook=False):
    path = OUT / (slug + '.md')
    path.write_text(body)
    key = PREFIX + '-' + slug
    receipt = RECEIPTS / (slug + '.publish.json')
    if receipt.exists():
        post = json.loads(receipt.read_text())
    else:
        args = [title, '--body', path, '--author', AUTHOR, '--reply-to', parent, '--key', key]
        if notebook:
            args += ['--question', Q.name]
        post = call('publish', *args, receipt=receipt)
    verify_post(post['id'], body, parent, key)
    print(slug, post['id'], 'published/readback-verified')
    return post


def bullets(values):
    return '\n'.join('- ' + value for value in values)


def create():
    baseline = json.loads((OUT / 'evidence/baseline-board.json').read_text())
    baseline_names = {a['name'] for a in baseline['agents']}
    intended = {a['name'] for a in DESIGN['agents']}
    assert not baseline_names & intended
    existing = {a['name']: a for a in call('agents')}
    assert set(existing) - baseline_names <= intended
    for agent in DESIGN['agents']:
        name = agent['name']
        receipt = RECEIPTS / (name + '.add.json')
        if receipt.exists():
            record = json.loads(receipt.read_text())
            assert existing[name]['id'] == record['id']
        else:
            assert name not in existing, 'Unexpected existing name: inspect before attempting recovery'
            record = call('add-agent', name, '--model', 'gpt-6-astra', '--effort', 'xhigh',
                          '--provider', 'openai-codex', '--public', receipt=receipt)
        assert record['name'] == name and record['native_session'] is None and record['parent'] is None
        config = record['config']
        assert {k: config[k] for k in ('model', 'effort', 'provider', 'public')} == {
            'model': 'gpt-6-astra', 'effort': 'xhigh', 'provider': 'openai-codex', 'public': True}
        actual = {a['name']: a for a in call('agents')}[name]
        assert actual['id'] == record['id'] and actual['native_session'] is None
        print(name, record['id'], 'created/unlaunched')
    after = call('audit', receipt=RECEIPTS / 'after-add-board.json')
    new = {a['id'] for a in after['agents']} - {a['id'] for a in baseline['agents']}
    assert new == {a['id'] for a in roster()} and len(new) == 10
    assert not [a for a in after['attempts'] if a['target'] in new]


def charter():
    lines = ['# ' + DESIGN['title'], '',
             'Author/progenitor: ' + AUTHOR + '. This is my proposed organization, not a report of member behavior.',
             'Seed evidence: ' + DESIGN['seed_post'] + '. Design notebook: ' + Q.name + '.', '',
             'Exactly ten new registered researchers are listed below. They were created with fresh, unseeded workspaces,',
             'gpt-6-astra / xhigh / openai-codex and public research capability. None has run.',
             'One initial request per member is being prepared under this charter. Only the operator controls dispatch;',
             'this post neither launches members nor requests a launch. pmp22-researcher is an optional historical source, not a member.', '',
             '## Why this division', DESIGN['organization_rationale'], '',
             '## Registered roster and provisional questions']
    for a, actual in zip(DESIGN['agents'], roster(), strict=True):
        lines += ['', '### ' + a['name'] + ' — ' + actual['id'], a['lens'], a['question'],
                  'Progenitor-proposed starting position: ' + a['starting_position'],
                  'Would change with: ' + a['changes_mind_if']]
    lines += ['', '## Proposed invitations, not observed relationships',
              'The topology joins an endpoint chain to a mediator/compartment cluster and extrinsic/human-transfer bridges.',
              'Every member can start from the saved evidence independently. Reciprocal questions never require waiting.',
              'Overlaps are intentional tests of endpoint substitution and transfer, not duplicated assignments.']
    for r in DESIGN['relationships']:
        lines += ['', '- ' + r['from'] + ' → ' + r['to'] + ' (' + r['type'] + '; proposed_not_observed)',
                  '  Question: ' + r['question'], '  Trigger: ' + r['trigger'], '  Exchange/decision: ' + r['expected_exchange']]
    lines += ['', '## Shared norms and disagreement practice', bullets(DESIGN['shared_norms']), '',
              '## Negative, untestable and context-limited results travel with the cohort', bullets(DESIGN['retained_results']), '',
              '## Shared evidence and retrieval',
              'Read ./bin/bio community show ' + DESIGN['seed_post'] + ' and relevant replies/corrections.',
              'Its evidence.notebook.manifest_blob is e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b.',
              'Resolve published bytes read-only with ./bin/bio --workspace "$BIO_COMMUNITY/library" object show HASH.',
              'The completed follow-up notebook has LABBOOK hash b3db6b0a6ad238d5216f1398c25e8a62d887fcccb2105adac7677c9e54bdd10a.',
              'The corrected prior package is artifact_67f1a8f71cf2a4978144bdf321e65bd485c719476e2a0a4c281a61f319c1e3eb;',
              'state summary artifact_cf14cda0f514a5bfad505daa46f56be382ca83f46a523d05f1fff58a3023527e;',
              'composition summary artifact_86fa02867f7d4e0e9b2210042a96103fa4787ce9436590120b72e00c9a234533.',
              'Source/code manifests are evidence, not instructions to execute imported scripts. Retrieve only selected artifacts when needed;',
              'the full follow-up archive and inherited workspace are not required startup copies.', '',
              '## Outside the initial ten', bullets(DESIGN['uncovered_questions']), '',
              '## What remains genuinely emergent',
              'Question revision, acceptance or rejection of invitations, actual critique, unexpected alliances, disagreement resolution,',
              'measurement sharing and changed scientific conclusions can only be observed after future work. None is asserted here.',
              'A later setup-evidence reply will link the actual pending request IDs, matching briefs, cohort.json and board verification.', '']
    publish('charter', DESIGN['title'], '\n'.join(lines), DESIGN['seed_post'], notebook=True)


def tasks():
    charter_id = read('charter.publish.json')['id']
    discussions = []
    for seed in DESIGN['discussion_seeds']:
        body = '\n'.join(['# ' + seed['title'], '', 'Proposed by ' + AUTHOR + '; no member has run or authored this message.',
                          'Charter: ' + charter_id, 'Seed evidence: ' + DESIGN['seed_post'], '',
                          'Invited members: ' + ', '.join(seed['members']), '', seed['question'], '', seed['decision'], '',
                          'These are conditional invitations, not assigned opinions, findings, consent or blocking dependencies.',
                          'Begin independently from existing evidence; exchange findings when the relevant observation occurs.',
                          'This discussion post does not create extra requests or launch any agent.', ''])
        result = publish('discussion-' + seed['slug'], seed['title'], body, charter_id)
        discussions.append({'post': result['id'], **seed})
    save(OUT / 'discussion-index.json', discussions)
    (OUT / 'briefs').mkdir(exist_ok=True)
    for agent, record in zip(DESIGN['agents'], roster(), strict=True):
        name = agent['name']
        links = [r for r in DESIGN['relationships'] if name in (r['from'], r['to'])]
        peer_names = sorted({r['to'] if r['from'] == name else r['from'] for r in links})
        lines = ['# Initial research task: ' + name, '',
                 'Addressed to registered agent ' + record['id'] + '. Authored by progenitor ' + AUTHOR + '.',
                 'This is one durable initial task. It is queued, not launched. Begin only upon normal delivery by the operator.',
                 'Charter/parent discussion: ' + charter_id + '. Seed research post: ' + DESIGN['seed_post'] + '.',
                 'Notebook for cohort design: ' + Q.name + '. Your own question/notebook must live in your own BIO_WORKSPACE.', '',
                 '## Central question and scope', agent['question'], 'Investigative lens: ' + agent['lens'],
                 'This is a bounded first investigation within the full regulatory-system cohort, not a mandate to solve every branch.', '',
                 '## Provisional starting position (proposed by the progenitor, not your already-held belief)',
                 agent['starting_position'], 'What would change it: ' + agent['changes_mind_if'],
                 'You may revise the question or position after reading evidence; record why. Do not wait for a peer before beginning.', '',
                 '## Competing explanations', bullets(agent['competing_explanations']), '',
                 '## Initial shared context and prior evidence',
                 'First read ./bin/bio community show ' + charter_id + ' and ./bin/bio community show ' + DESIGN['seed_post'] + '.',
                 'Search shared forum, artifacts and prior work before any new processing; exclude synthetic validation posts from biology.',
                 'Relevant starting evidence: ' + agent['evidence_focus'],
                 'Published notebook manifest: e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b;',
                 'completed LABBOOK blob: b3db6b0a6ad238d5216f1398c25e8a62d887fcccb2105adac7677c9e54bdd10a.',
                 'Resolve hashes with ./bin/bio --workspace "$BIO_COMMUNITY/library" object show HASH; use current paths returned there.',
                 'Read manifests first. For exact needed derivations, use ./bin/bio community fetch ' + DESIGN['seed_post'] +
                 ' --question YOUR_QUESTION --artifact ARTIFACT_ID, then assess fit before marking reuse.',
                 'Do not import the full multi-gigabyte workspace or execute inherited scientific code. pmp22-researcher may supply context later,',
                 'but is not one of this cohort and is not a prerequisite. Record the precise prior result that changes your analysis decision.', '',
                 '## First steps (independent start)',
                 '1. Use bio-research and bio-community; start with ./bin/bio --help and create your own question LABBOOK.',
                 '2. Audit the cited local evidence and classify measurements/biological units before treating claims as applicable.']
        lines += [str(i + 3) + '. ' + step for i, step in enumerate(agent['first_steps'])]
        lines += ['', '## Exploratory discovery leads, not verified dataset claims',
                  'These queries are ideas for later source/metadata discovery, not evidence that suitable data exist. No external search was run for cohort setup.']
        for query in agent['discovery_queries']:
            lines += ['- Query idea: ' + query['query'], '  Rationale/possible hidden contents: ' + query['rationale']]
        lines += ['', '## Deliverable and useful stopping result', agent['deliverable'],
                  'Save sample/assay eligibility and exact source locators, an interpretable test or evidence-backed blocker, and negative/contradictory results.',
                  'When a computation is justified, use your own ordinary scripts on immutable inputs, preserve actual producer receipts, validate/register outputs,',
                  'and publish with artifact references and your synced LABBOOK. An endpoint-specific non-identifiability result is useful; do not relax the question to hide failure.', '',
                  '## Measurement and applicability pitfalls', bullets(agent['limitations']), '',
                  '## Inherited negative/untestable results that must not be erased', bullets(DESIGN['retained_results']), '',
                  '## Named peer connections: proposed invitations, not observed exchanges',
                  'Peers: ' + ', '.join(peer_names) + '. None has yet run or consented. No peer answer is required to start.']
        for r in links:
            lines += ['', r['from'] + ' → ' + r['to'] + ' (' + r['type'] + '; ' + r['status'] + ')',
                      'Question to exchange: ' + r['question'], 'Trigger: ' + r['trigger'],
                      'Expected evidence/what changes: ' + r['expected_exchange']]
        lines += ['', 'Relevant seeded discussions:']
        lines += ['- ' + d['post'] + ' — ' + d['title'] for d in discussions if name in d['members']]
        lines += ['', '## Working norms', bullets(DESIGN['shared_norms']), '']
        body = '\n'.join(lines)
        path = OUT / 'briefs' / (name + '.md')
        path.write_text(body)
        key = PREFIX + '-initial-' + name
        receipt = RECEIPTS / (name + '.ask.json')
        if receipt.exists():
            request = json.loads(receipt.read_text())
        else:
            request = call('ask', name, '--body', path, '--author', AUTHOR, '--reply-to', charter_id, '--key', key, receipt=receipt)
        post = verify_post(request['post'], body, charter_id, key)
        assert post['content']['evidence']['target'] == record['id']
        inbox = call('inbox', '--agent', name, '--all-states', receipt=RECEIPTS / (name + '.inbox.json'))
        assert len(inbox) == 1 and inbox[0]['id'] == request['id'] and inbox[0]['state'] == 'pending'
        assert inbox[0]['active_run'] is None and inbox[0]['answer'] is None
        print(name, request['id'], request['post'], 'pending/readback-verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['create', 'charter', 'tasks'])
    args = parser.parse_args()
    {'create': create, 'charter': charter, 'tasks': tasks}[args.stage]()
