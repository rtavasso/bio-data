"""Initialize question-local, agent-authored investigation checkpoint before discovery."""
from pathlib import Path
import datetime
import json
import subprocess

Q = Path(__file__).resolve().parents[1]
O = Q / 'outputs'
I = Q / 'inputs'
I.mkdir(exist_ok=True)

def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')

nodes = [('perturbation', 'Nae1 or mTOR perturbation'), ('state', 'Schwann developmental/repair state'), ('mixture', 'Relative cell and RNA composition'), ('antioxidant', 'Antioxidant RNA abundance'), ('pmp22', 'Pmp22 total RNA'), ('nrf2', 'NRF2 activity (unmeasured)')]
edges = [('perturbation-state', 'perturbation', 'state'), ('perturbation-mixture', 'perturbation', 'mixture'), ('state-antioxidant', 'state', 'antioxidant'), ('mixture-antioxidant', 'mixture', 'antioxidant'), ('state-pmp22', 'state', 'pmp22'), ('mixture-pmp22', 'mixture', 'pmp22'), ('perturbation-nrf2', 'perturbation', 'nrf2'), ('nrf2-antioxidant', 'nrf2', 'antioxidant'), ('nrf2-pmp22', 'nrf2', 'pmp22')]
m = dict(revision=1, scope=dict(target='PMP22', endpoint='Total RNA and antioxidant RNA contrast, not promoter output/protein', context='GSE241269 P7 mouse whole nerve versus Figlia2017 P5 mTOR conditional knockouts; references assessed separately', assumptions='No causal or cross-species transfer assumed'), nodes=[dict(id=i, label=l, kind='hypothesized_variable') for i, l in nodes], edges=[dict(id=i, source=s, target=t, mechanism='Competing explanation to audit', context='Initial hypothesis, not established by recalled knowledge', status='hypothesis', evidence=[]) for i, s, t in edges], frontier=[dict(node=x, question='Can this explain the source contrast?', priority='High', reason='Unresolved in inherited investigation', status='open') for x in ['state', 'mixture', 'nrf2']], changes=[])
for p in ['mechanisms.initial.json', 'mechanisms.json']:
    save(O / p, m)
items = []
for ident, question, readout, assets, step in [
    ('inherited-baseline', 'Do the exact inherited derivations support the contrast being explained?', 'Native cells, sample metadata and immutable artifacts', ['q_277f20df4b6b47cc','GSE241269','PMC5589416'], 'Audit source cells and attach fitting artifacts'),
    ('purified-state-reference', 'Can state changes within purified Schwann cells reproduce the antioxidant/myelin pattern?', 'Processed purified developmental or repair transcriptomes with known sample units', ['GSE177037'], 'Compare developmental and repair reference metadata before substantial acquisition'),
    ('bulk-sensitivity', 'Does the contrast remain under defensible state/composition sensitivities in the existing bulk matrices?', 'Sample scores, reference projections and broad effects', ['GSE241269','PRJEB20661'], 'Preserve sensitivity plan before new outcome inspection; then run per-study analyses'),
    ('cell-composition', 'Can measured cell-type reference profiles and plausible mixtures account for the contrast?', 'Annotated cell-type RNA profiles; biological replicate metadata; mixture bounds', [], 'Search assay/state/design terms and inspect processed references, not target-name-only sources'),
    ('causal-identification', 'What remains unidentifiable about NRF2 and PMP22 regulation?', 'Matched within-cell perturbation/rescue and calibrated RNA/protein readouts', ['PMC11014456','PMC5589416'], 'Inspect design limitations; do not substitute covariate adjustment for causal proof')]:
    items.append(dict(id=ident, priority='high', question=question, alternatives=['Composition or state suffices', 'Parallel/perturbation-associated redox response', 'Unresolved design or measurement confounding'], readout=readout, assets=assets, prerequisites=['Source/sample/feature eligibility and independence audit'], status='open', artifacts=[], finding='', limitation='Not yet analyzed in this follow-up', next_action=step, blocker_evidence=[]))
x = dict(revision=1, scope=m['scope']['endpoint'], status='in_progress', stopping_reason='No time or transport cap; continue informative feasible work', items=items)
for p in ['investigations.r001.json', 'investigations.json']:
    save(O / p, x)
(Q / 'LABBOOK.md').write_text('''# Cell composition and developmental state follow-up
Question: q_b6e71fffe204498a

## Intake and scope
Started with ./bin/bio --help; supplied wrappers only. No inputs/source-context.json exists. Work is confined to this checkout. No repository/application/evaluation/skill changes and no other agents. New question, not a replacement for the broad prior investigation.

Retrieved prior q_277f20df4b6b47cc through work/artifact searches and read its entire LABBOOK, corrected retrieval pointer, antioxidant scripts, artifact manifest, and primary Figlia/Nae1 source text. Native session search returned 20260929_133701_bc632e and 20260929_155427_f27806; corrected archive supersedes stronger wording and retracted browser claims in the older session. Prior full schema and prediction-link checks pass. No always-on scientific memory entry was supplied; task findings belong in this archive, not persona memory.

The inherited four-gene effect is retrospective and context-limited, not evidence of perturbation specificity or NRF2 causation. The five-gene lock remains untestable because Osgin1 violates its frozen baseline floor. Nae1 relative-preservation prediction failed. Ppp6r1/Gtf2f1/Hck transfer negatives, Eed truncation, HDAC3 HIDATA, opposed ISR contexts and protein quantitation limits remain unchanged. Exact reusable matrices and sources will be audited before use, rather than trusting this summary.

## Initial decision checkpoint (before broad discovery)
Hypotheses: altered cell/RNA fractions; Schwann developmental or repair state; parallel redox response to neddylation; direct NRF2 mediation (unidentified). RNA fractions are not cell counts or absolute abundance. Shared myelin loss does not prove equal states. Follow inherited GSE177037 purified-cell lead, but its P18 rat crush design is a repair reference, not a neonatal developmental series. Seek a closer developmental reference and a cell-type atlas independently. Compare metadata before substantial acquisition. Incidental full transcriptomes can test state without being collected to study antioxidants; selected marker tables cannot.

Reserve most effort for actual reference and bulk analyses, source audits, sensitivity and consolidation, not literature enumeration. No research time limit or finite retrieval allowance. Record actual request receipts; browser payload size may be unknown. New computational outputs require producer-specific receipts and exact input/code registration.

Initial map and queue saved before new public discovery. No newly chosen reference outcomes inspected yet. Inherited bulk outcomes and GSE177037 target/state patterns are already exposed, so those tests are retrospective. A detailed falsifiable sensitivity plan will be preserved after metadata-based reference choice and before new outcome inspection when feasible.
''')
receipts = []
for p in [O / 'mechanisms.initial.json', O / 'investigations.r001.json']:
    r = subprocess.run(['./bin/bio', 'object', 'add', str(p), '--classification', 'interpretation'], text=True, capture_output=True, check=True)
    receipts.append(dict(path=str(p.relative_to(Q)), receipt=json.loads(r.stdout)))
save(O / 'checkpoint-r001-preservation.json', receipts)
print(json.dumps(dict(started=datetime.datetime.now(datetime.timezone.utc).isoformat(), question=Q.name, preserved=receipts), indent=2))
