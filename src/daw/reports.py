from collections import Counter
import json

from jinja2 import Environment, select_autoescape

TEMPLATE = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{{ request.question_id }} · Data Archaeology Workbench</title>
<style>
:root{--ink:#18332f;--paper:#f4f3ec;--line:#d3d9cd;--green:#236958;--amber:#9a6321;--muted:#62736b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 ui-sans-serif,system-ui,sans-serif}
header{background:var(--ink);color:#eff3df;padding:28px max(6vw,24px)}.brand{font:12px ui-monospace,monospace;letter-spacing:.17em;text-transform:uppercase}
.mast{display:flex;justify-content:space-between;gap:30px;align-items:end}h1{font-size:clamp(30px,4vw,54px);line-height:1.08;letter-spacing:-.045em;font-weight:500;margin:38px 0 18px;max-width:1000px}
.subtitle{color:#b4c5b1;max-width:780px}main{max-width:1500px;padding:32px max(6vw,24px) 70px;margin:auto}
.run{font:11px ui-monospace,monospace;overflow-wrap:anywhere;color:#b4c5b1}.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);margin-bottom:32px;background:#fafaf4}.stat{padding:23px;border-right:1px solid var(--line)}.stat:last-child{border:0}.stat strong{display:block;font-size:38px;line-height:1.2;font-weight:500}.stat span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.07em}
h2{font-size:23px;font-weight:500;letter-spacing:-.02em;margin:30px 0 4px}.caption{color:var(--muted);font-size:13px;margin:4px 0 18px}.note{padding:16px 20px;border-left:3px solid var(--amber);background:#ebe6d8;margin:22px 0}.toolbar{display:flex;gap:10px;margin:20px 0;flex-wrap:wrap}input,select{font:inherit;padding:10px 12px;border:1px solid var(--line);background:#fafaf4;color:var(--ink);border-radius:4px}input{flex:1;min-width:220px}.table-wrap{overflow:auto;border:1px solid var(--line);max-height:640px}table{border-collapse:collapse;width:100%;font-size:13px}th{background:#e8ede1;position:sticky;top:0;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.07em;white-space:nowrap}th,td{padding:13px 15px;border-bottom:1px solid var(--line);vertical-align:top}td{max-width:550px;overflow-wrap:anywhere}tr:last-child td{border-bottom:0}.badge{display:inline-block;border-radius:3px;padding:3px 7px;font:11px ui-monospace,monospace;white-space:nowrap;background:#e2e9dc}.pending,.unresolved{background:#efe1c8;color:#82500f}.not_measurable{background:#e3e3e0;color:#575d55}.evaluated_detected{background:#d6e8dc;color:#1c634a}.mono{font:11px ui-monospace,monospace}.number{font:14px ui-monospace,monospace;font-variant-numeric:tabular-nums}.downloads{display:flex;gap:10px;flex-wrap:wrap}.downloads a{border:1px solid var(--line);padding:8px 12px;color:var(--green);text-decoration:none}.empty{padding:35px;color:var(--muted);border:1px dashed var(--line)}footer{margin-top:36px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}details{margin-top:15px}summary{cursor:pointer;color:var(--green)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#e8ede1;padding:18px}
@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}.stat{border-bottom:1px solid var(--line)}.mast{display:block}}
</style>
<header><div class="brand">DAW / Data Archaeology Workbench</div><div class="mast"><div><h1>{{ request.question_id }}</h1>
<p class="subtitle">Recover the measurement. Preserve its context. Keep the unknown visible.</p></div><div class="run">IMMUTABLE QUERY RECEIPT<br>{{ run }}</div></div></header>
<main><div class="stats"><div class="stat"><strong>{{ plan.denominator }}</strong><span>Frozen candidates</span></div>
<div class="stat"><strong>{{ measured_candidates }}</strong><span>Evaluated representations</span></div><div class="stat"><strong>{{ measurements|length }}</strong><span>Extracted measurements</span></div><div class="stat"><strong>{{ unfinished }}</strong><span>Pending / unresolved</span></div></div>
<div class="brand">{{ request.operator }}</div><p class="caption">{{ plan.scope }}. Candidate set <span class="mono">{{ plan.candidate_set_digest[:16] }}</span></p>
<div class="note">A row match or extracted value is a measurement, not a significance or causal claim. Missing rows in selected tables remain unresolved. Coverage describes this saved candidate set, not all public evidence.</div>
<h2>Measurement ledger</h2><p class="caption">Native values, kept separate by source representation. Displaying up to 500 rows; the Parquet package contains all accepted rows.</p>
{% if measurements %}<div class="table-wrap"><table><thead><tr><th>Feature / field</th><th>Value</th><th>Source locator</th><th>Criterion</th><th>Provenance</th></tr></thead><tbody>
{% for m in measurements[:500] %}<tr><td>{{ m.feature or '' }}<br><span class="mono">{{ m.field or '' }}</span></td><td class="number">{{ m.value if m.value is not none else m.text or 'unresolved' }}</td><td class="mono">{{ m.locator or 'see context' }}</td><td>{{ m.criterion or 'descriptive extraction' }}</td><td class="mono">{{ m.asset_revision }}<br>{{ m.measurement_id[:16] }}<details><summary>Details</summary>{{ m.details_json }}</details></td></tr>{% endfor %}</tbody></table></div>{% else %}<div class="empty">No measurements were accepted for this request. The coverage ledger records why each candidate could not answer it.</div>{% endif %}
<h2>Experimental context</h2><p class="caption">Interpretations stay separate by representation. Repeated source rows and alternate files are not independent biological replicates. Long collections are abbreviated here; the context download preserves them in full.</p>
{% for c in contexts %}<details><summary>{{ c.name }} · {{ c.units }} · {{ c.selector_json }}</summary><p class="mono">Source {{ c.source_blob }}<br>Interpretation {{ c.curation_digest }}</p><pre>{{ c.display_settings }}</pre><details><summary>Source metadata</summary><pre>{{ c.source_metadata_json }}</pre></details></details>{% endfor %}
<h2>Coverage & remaining work</h2><p class="caption">All {{ coverage|length }} candidates, including unacquired assets and uncurated workbook sheets.</p>
<div class="toolbar"><input id="search" type="search" placeholder="Filter by source, reason, or sheet…" aria-label="Search coverage"><select id="state" aria-label="Filter result state"><option value="">All result states</option>{% for state in states %}<option>{{ state }}</option>{% endfor %}</select></div>
<div class="table-wrap"><table id="coverage"><thead><tr><th>Resource / scope</th><th>Acquisition</th><th>Inspection</th><th>Capability</th><th>Result</th><th>Reason / next prerequisite</th></tr></thead><tbody>
{% for c in coverage %}<tr data-state="{{ c.result_state }}"><td>{{ c.name }}<br><span class="mono">{{ c.selector_json }}</span></td><td>{{ c.acquisition }}</td><td>{{ c.inspection }}</td><td>{{ c.capability }}</td><td><span class="badge {{ c.result_state }}">{{ c.result_state }}</span></td><td>{{ c.reason }}</td></tr>{% endfor %}
</tbody></table></div><p id="visible" class="caption" aria-live="polite">{{ coverage|length }} candidates shown</p>
<h2>Reproducible package</h2><p class="caption">These local files preserve the request, frozen plan, numerical results, context, and provenance.</p>
<div class="downloads">{% for name in downloads %}<a href="{{ name }}" download>{{ name }}</a>{% endfor %}</div>
<details><summary>Validation receipt</summary><pre>{{ validation }}</pre></details>
<footer>Private · local · no remote scripts, fonts, trackers, or model calls. This is a historical result; refresh and corrected interpretations create new runs. Check <a href="current_status.json">current catalog status</a> when this report is regenerated.</footer></main>
<script>const input=document.getElementById('search'),state=document.getElementById('state');function filter(){let n=0;for(const row of document.querySelectorAll('#coverage tbody tr')){const show=row.textContent.toLowerCase().includes(input.value.toLowerCase())&&(!state.value||row.dataset.state===state.value);row.hidden=!show;if(show)n++}document.getElementById('visible').textContent=n+' candidates shown'}input.addEventListener('input',filter);state.addEventListener('change',filter);</script></html>"""


def html_report(run, request, plan, measurements, coverage, validation, contexts=()):
    def compact(value):
        if isinstance(value, dict):
            entries = list(value.items())
            result = {k: compact(v) for k, v in entries[:24]}
            if len(entries) > 24:
                result["… additional entries in context download"] = len(entries) - 24
            return result
        if isinstance(value, list):
            result = [compact(v) for v in value[:24]]
            return result + [f"… {len(value) - 24} more in context download"] if len(value) > 24 else result
        return value
    env = Environment(autoescape=select_autoescape(default=True))
    counts = Counter(c["result_state"] for c in coverage)
    names = {c["asset_revision"]: c["name"] for c in coverage}
    context_display = [{**c, "name": names[c["asset_revision"]],
                        "display_settings": json.dumps(compact(json.loads(c["settings_json"])), indent=2, ensure_ascii=False)} for c in contexts]
    return env.from_string(TEMPLATE).render(run=run, request=request, plan=plan, measurements=measurements, contexts=context_display,
        coverage=coverage, states=sorted(counts), measured_candidates=sum(c["measurements"] > 0 for c in coverage),
        unfinished=counts["pending"] + counts["unresolved"], validation=validation,
        downloads=["request.json", "plan.json", "measurements.parquet", "measurement_context.parquet",
                   "coverage.parquet", "provenance.json", "validation.json"])
