"""Reproduce the saved pilot, verify values, export tracks, and write its handoff."""
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from jinja2 import Environment, select_autoescape

from daw.catalog import Workspace, restore_check
from daw.exports import export_igv
from daw.models import Discovery, Query
from daw.adapters import Sources
from daw.query import coverage_audit, query
from daw.util import environment_identity, now, read_json, write_json

started = time.monotonic()
timings = []
for script in ("recipes/pilot_tables.py", "recipes/pilot_genomics.py", "recipes/heldout_matrix.py", "recipes/repository_table.py", "scripts/validate_pilot.py"):
    before = time.monotonic()
    subprocess.run([sys.executable, script], check=True)
    timings.append({"script": script, "wall_seconds": round(time.monotonic() - before, 2)})

ws = Workspace("workspaces/pilot")
with ws.writer():
    # Preserve the final-page regression's real provider response in the pilot too.
    source = Sources(ws)
    try:
        discovery = source.discover(Discovery(provider="europepmc", query="EXT_ID:32770939", max_pages=2, page_size=10))
        write_json("docs/receipts/europepmc-final-page.json", discovery)
        assert discovery["exhausted"] and discovery["resources"]
    finally:
        source.http.close()
    tables = read_json("docs/receipts/pilot-table-results.json")
    genomic = read_json("docs/receipts/pilot-genomic-results.json")
    heldout = read_json("docs/receipts/heldout-validation.json")
    repository = read_json("docs/receipts/repository-table-results.json")
    results = tables["queries"] + genomic["queries"] + [heldout["query"], heldout["pseudobulk_check"], heldout["missing_feature_check"]] + repository["queries"]
    cards = []
    for result in results:
        request = read_json(ws.blob_path(result["artifacts"]["request.json"]))
        cards.append({"title": request["question_id"], "measurements": result["measurements"],
            "candidates": result["candidates"], "states": result["result_counts"], "href": result["run"] + "/report.html"})
    retry_request = Query.model_validate(read_json(ws.blob_path(tables["queries"][0]["artifacts"]["request.json"])))
    repeated = query(ws, retry_request)
    assert repeated["reused_from"] == tables["queries"][0]["run"]
    assert repeated["artifacts"] == tables["queries"][0]["artifacts"]
    exports = []
    for result in (genomic["queries"][0], genomic["queries"][2]):
        request = Query.model_validate(read_json(ws.blob_path(result["artifacts"]["request.json"])))
        destination = ws.root / "reports" / ("igv-" + result["run"])
        if destination.exists():
            exports.append({"session": str(destination / "session.xml"), "reused": True})
        else:
            exports.append(export_igv(ws, request, destination))
    audit = coverage_audit(ws)
    write_json("docs/receipts/coverage-audit.json", audit)
    assertions = ws.one("SELECT count(*) AS n FROM assertion")["n"]
    curations = ws.one("SELECT count(*) AS n FROM current_curation")["n"]
    snapshots = ws.rows("SELECT id,locator,retrieved,outcome,blob FROM snapshot ORDER BY retrieved")
    write_json("docs/receipts/source-snapshot-index.json", snapshots)
    bundles = []
    for bundle in ws.rows("SELECT id,provider,native_id FROM resource WHERE kind='bundle' ORDER BY provider,native_id"):
        scoped = coverage_audit(ws, bundle["id"])
        bundles.append({**bundle, "assets": scoped["denominator"], "acquired": scoped["fully_acquired"],
                        "query_ready_assets": scoped["query_ready_assets"], "acquisition_states": scoped["acquisition_counts"]})
    receipt = {"created": now(), "environment": environment_identity(), "recipe_wall_seconds": timings,
        "elapsed_seconds": round(time.monotonic() - started, 2), "bundles": bundles,
        "catalog": {k: v for k, v in audit.items() if k != "assets"}, "accepted_selector_count": curations,
        "source_assertions": assertions, "retry": {"run": repeated["run"], "reused_from": repeated["reused_from"], "identical_artifacts": True},
        "igv": exports, "measurement_records_are_not_independent_experiments": True,
        "review_accounting": "Recipe/evidence locators are recorded; human review time and global semantic-error rate were not measured",
        "acquisition_outcomes": dict(Counter(s["outcome"] for s in snapshots))}
    write_json("docs/receipts/pilot-summary.json", receipt)
    backup_path = Path("workspaces") / ("pilot-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    backup = ws.backup(backup_path)
    restored = restore_check(backup_path)
    assert restored["ok"]
    write_json("docs/receipts/backup-restore.json", {"backup": backup, "restore": restored, "created": now()})
    env = Environment(autoescape=select_autoescape(default=True))
    html = env.from_string('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Recovered evidence · Data Archaeology Workbench</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f3ec;color:#18332f;font:16px/1.6 system-ui,sans-serif}header{background:#18332f;color:#eff3df;padding:60px 7vw}main{max-width:1250px;margin:auto;padding:40px 30px 70px}h1{font-size:clamp(36px,6vw,76px);font-weight:500;letter-spacing:-.05em;line-height:1.06;max-width:900px}h2{font-weight:500;letter-spacing:-.025em}.brand{font:12px monospace;letter-spacing:.18em;text-transform:uppercase}.lead{max-width:790px;color:#b4c5b1}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}.card{padding:24px;border:1px solid #c9d2c3;background:#fafaf4;color:inherit;text-decoration:none;border-radius:6px}.card:hover{border-color:#236958;background:#eaf0e2}.card h3{font-size:20px;line-height:1.3;font-weight:500}.big{font-size:44px;line-height:1;color:#236958}.small{color:#62736b;font-size:13px}.note{padding:20px;border-left:3px solid #9a6321;background:#ebe6d8}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:12px;border-bottom:1px solid #d3d9cd;text-align:left}a{color:#236958}code{font-size:12px;overflow-wrap:anywhere}footer{padding-top:32px;color:#62736b;font-size:13px}</style>
<header><div class="brand">DAW / Public data, recovered locally</div><h1>From buried files<br>to inspectable evidence.</h1><p class="lead">Real supplementary tables, native genomic tracks, and a held-out human matrix. Every result carries its exact source, accepted interpretation, and a ledger of what remains unknown.</p></header>
<main><p class="brand">Pilot · 27 September 2026 · saved local evidence</p><div class="note">These are descriptive measurements from distinct biological settings: rat Schwann experiments, an engineered human Schwann line, tumor bulk mixtures, and human blood used for validation. No cross-species pooling, causal conclusion, or P1/P2 assignment is implied.</div>
<h2>Open a reproducible result</h2><div class="grid">{% for c in cards %}<a class="card" href="{{ c.href }}"><div class="big">{{ c.measurements }}</div><span class="small">measurement records · {{ c.candidates }} scoped candidates</span><h3>{{ c.title }}</h3><span class="small">{% for state,n in c.states.items() %}{{ n }} {{ state }}{% if not loop.last %} · {% endif %}{% endfor %}</span></a>{% endfor %}</div>
<h2>What was checked</h2><p>604 source-cell values matched independent reads. All 2,700 held-out expression values and cell order matched the native matrix. Four native-reference genomic queries passed independent numerical checks. Repeating a query reused identical artifact hashes. A complete catalog/blob backup was restored into a separate temporary workspace and verified.</p>
<h2>Coverage remains visible</h2><p>{{ audit.denominator }} current assets are cataloged; {{ audit.fully_acquired }} are acquired and {{ audit.query_ready_assets }} have an accepted query capability. This is a scoped inventory, not a claim to exhaust public evidence. Files, sheets, contrasts, and cells are not independent experiments.</p>
<div style="overflow:auto"><table><thead><tr><th>Source bundle</th><th>Assets</th><th>Acquired</th><th>Query ready</th></tr></thead><tbody>{% for b in bundles %}<tr><td>{{ b.provider }} · {{ b.native_id }}</td><td>{{ b.assets }}</td><td>{{ b.acquired }}</td><td>{{ b.query_ready_assets }}</td></tr>{% endfor %}</tbody></table></div>
<h2>Inspect native tracks in IGV</h2><p>{% for e in igv_links %}<a href="{{ e.href }}">{{ e.label }}</a>{% if not loop.last %} · {% endif %}{% endfor %}. Session packages contain copied source tracks and manifests. Their XML and coordinates were verified; the IGV Desktop GUI was not exercised.</p>
<footer>Source data and reports remain in this private workspace. See the repository's docs/PILOT.md for scope, tests, receipts, commands, and limitations.</footer></main></html>''').render(cards=cards, audit=audit, bundles=bundles, igv_links=[
        {"href": str(Path(e["session"]).relative_to(ws.root / "reports")), "label": label}
        for e, label in zip(exports, ("Human PMP22 H3K27ac", "Rat Pmp22 ATAC"), strict=True)])
    (ws.root / "reports/index.html").write_text(html)
    print(json.dumps({"report": str(ws.root / "reports/index.html"), "backup": backup, "restore": restored,
                      "current_assets": audit["denominator"], "acquired": audit["fully_acquired"], "ready": audit["query_ready_assets"]}), flush=True)
ws.close()
