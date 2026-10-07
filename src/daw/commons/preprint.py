"""Preprint export (spec v2 V7): a write-up with its cited claims and artifact bytes as a static,
content-addressed site that a reader verifies offline.

`export_preprint(board, actor, post)` (permission `export`) writes:

```
index.html            the write-up (untrusted, escaped, no scripts); every number marked with its checker
                      status; pointers open the claim or artifact; figures link to their artifact bytes
claims.html           every cited claim (text, scope, status, its own pointers), local or of another snapshot
artifacts/<key>.html  one page per artifact: sha256, output bytes, manifest (local or foreign)
artifacts/<key>/...   the output bytes and the manifest (server paths stripped)
verification.html     the checker's verdict per number, the value found at each pointer and a byte link (no JS)
preprint.json         machine-readable: the post record hash, every number with offsets, pointers, locators,
                      recorded results, and where each claim and artifact lives in this snapshot
source/<post>.md      the write-up's Markdown, exactly as stored (number offsets are code points into it)
records/<post>.json   the exact bytes of the post's content blob (sha256 = the post's body_blob)
checks/<post>.json    the checker's verdict record (as in every export)
records.json          claims and artifacts of this snapshot, for federation indexes
verify.py             a standalone verifier (Python standard library only; `daw.commons.preprint_verify`)
style.css  snapshot.json  snapshot.id
```

The snapshot ID is the sha256 of `snapshot.json` (format `colloquy.snapshot/1`, scope `preprint`), so the
preprint is cited by bytes and imports into another commons like any snapshot; its claims are then cited as
`snapshot:<id>/claim_…`. Citations of other snapshots inside the write-up keep their snapshot id, and the
cited foreign bytes are included under their own keys.

A preprint must be verifiable offline, so the export refuses (and names what is missing) when the write-up
is hidden or refused by the checker, or when a cited artifact's bytes cannot be included: unpublished
(only in a participant workspace), absent from this archive, or a foreign record whose snapshot is not
imported. Nothing is executed; values are checked by `daw.commons.locators` at export and by `verify.py`
again on the reader's machine.
"""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from daw.commons import export, federation, views, writeup
from daw.commons.archive import Archive
from daw.commons.permissions import require
from daw.util import DawError, canonical

FORMAT = "colloquy.preprint/1"
VERIFIER = Path(__file__).with_name("preprint_verify.py")


def _key(identity):
    """A file-system key for a local or foreign record: `artifact_…` or `<snapshot[:12]>-artifact_…`."""
    parts = federation.split(identity)
    return f"{parts[0][:12]}-{parts[1]}" if parts else identity


def _artifact(view, identity, entry):
    """(record for preprint.json, files {path: bytes}) for one cited artifact, or raises the reason it cannot be
    included."""
    key = _key(identity)
    if entry.get("foreign"):
        data, name, reason = federation.artifact_output(view, identity)
        if data is None:
            raise DawError("preprint_bytes_unavailable", f"{identity}: {reason}")
        name = export.safe_component(Path(str(name or "output")).name)
        path = f"artifacts/{key}/{name}"
        manifest_path = None
        record = {"id": identity, "snapshot": entry["snapshot"], "title": entry.get("title"), "name": name,
                  "path": path, "sha256": entry["sha256"], "bytes": len(data), "manifest_path": manifest_path,
                  "output_role": entry.get("output_role"), "foreign": True}
        return record, {path: data}
    location = entry.get("location") or {}
    if location.get("store") != "library":
        raise DawError("preprint_unpublished_evidence",
                       f"{identity} is only in a participant workspace; publish it with a post before a preprint "
                       "cites it")
    row = view.library.one("SELECT * FROM artifact WHERE id=?", (identity,))
    manifest = export._library_json(view, row["manifest_blob"])
    data = export._library_bytes(view, row["output_blob"])
    if data is None:
        raise DawError("preprint_bytes_unavailable", f"{identity}: the output bytes are not in this archive "
                                                     "(present: false)")
    name = export.safe_component(Path(str((manifest.get("output") or {}).get("name") or row["output_blob"])).name)
    path, manifest_path = f"artifacts/{key}/{name}", f"artifacts/{key}/manifest.json"
    files = {path: data, manifest_path: canonical({"artifact": identity, "manifest_blob": row["manifest_blob"],
                                                    "output_blob": row["output_blob"],
                                                    "manifest": export._strip_paths(manifest)})}
    record = {"id": identity, "title": manifest.get("title"), "name": name, "path": path, "sha256": row["output_blob"],
              "bytes": len(data), "manifest_path": manifest_path, "output_role": row["output_role"],
              "derivation_key": row["derivation_key"], "summary": manifest.get("summary")}
    return record, files


def _claim(entry):
    record = {"id": entry["id"], "text": entry.get("text") or "", "scope": entry.get("scope") or {},
              "status": entry.get("status"), "post": entry.get("post"), "post_title": entry.get("post_title"),
              "pointers": [{k: p.get(k) for k in ("kind", "id", "locator") if p.get(k) is not None}
                           for p in entry.get("pointers") or []]}
    if entry.get("foreign"):
        record.update(snapshot=entry["snapshot"], foreign=True)
    return record


def build_preprint(view, post_id):
    """(site, manifest, summary) of a preprint. Pure function of the archive state."""
    row = view.one("SELECT * FROM post WHERE id=?", (post_id,))
    if not row:
        raise DawError("unknown_post", post_id)
    vis = views.visibility(view)
    if vis.withheld(post_id):
        raise DawError("hidden_by_moderation", post_id)
    rendered = writeup.render_writeup(view, post_id, with_map=False)
    if rendered["status"] == "refused":
        kinds = sorted({p.get("kind") for p in rendered.get("problems") or []})
        raise DawError("preprint_refused", f"the number checker refused this write-up ({', '.join(kinds)})")
    record_bytes = export._library_bytes(view, row["body_blob"])
    if record_bytes is None:
        raise DawError("preprint_bytes_unavailable", "the post's content blob is not in this archive")
    content = json.loads(record_bytes)
    source = content.get("body") or ""
    pointers = rendered["pointers"]
    people = views.thread_index(view)["people"]

    site = export.Site()
    artifacts, claims, posts = {}, {}, {}
    missing = []
    # Cited records, plus the artifacts the cited claims point at ("its cited claims, artifacts").
    wanted = [(i, e) for i, e in sorted(pointers.items()) if e.get("present")]
    for identity, entry in list(wanted):
        if entry["kind"] == "claim":
            if entry.get("hidden"):
                missing.append(f"{identity}: the claim's post is hidden by moderation")
                continue
            claims[identity] = _claim(entry)
            for p in entry.get("pointers") or []:
                pid = p.get("id") or ""
                if entry.get("foreign") or not writeup.CITABLE["artifact"].fullmatch(pid) or pid in pointers:
                    continue
                wanted.append((pid, writeup.resolve_pointer(view, pid, "artifact", {})))
    for identity, entry in wanted:
        if entry["kind"] == "artifact" and identity not in artifacts:
            if not entry.get("present"):
                missing.append(f"{identity}: not catalogued")
                continue
            try:
                record, files = _artifact(view, identity, entry)
            except DawError as error:
                missing.append(error.detail)
                continue
            artifacts[identity] = record
            for path, data in files.items():
                site.add(path, data)
        elif entry["kind"] == "post":
            posts[identity] = {"id": identity, "title": entry.get("title"), "hidden": bool(entry.get("hidden"))}
    absent = [i for i, e in pointers.items() if not e.get("present")]
    if absent or missing:
        raise DawError("preprint_unverifiable", "; ".join(missing + [f"{i}: does not resolve" for i in absent]))

    numbers = []
    for n in rendered["numbers"]:
        refs = []
        for p in n["pointers"]:
            if p.get("kind") not in writeup.COVERING:
                continue
            refs.append({k: p[k] for k in ("kind", "id", "locator", "result", "at", "reason", "found") if p.get(k) is not None}
                        | {"ref": p["id"]})
        numbers.append({k: n[k] for k in ("text", "offset", "length", "line", "scope", "status")} | {"pointers": refs})

    # Pages.
    def page_of(identity):
        if identity in artifacts:
            return f"artifacts/{_key(identity)}.html"
        if identity in claims:
            return f"claims.html#{_key(identity)}"
        return None

    def linker(page):
        def link(target):
            found = page_of(target)
            return export._rel(page, found) if found else None
        return link

    def bytes_link(page):
        def link(target):
            return export._rel(page, artifacts[target]["path"]) if target in artifacts else None
        return link

    def image(page):
        def src(target):
            item = artifacts.get(target)
            if item and item["name"].lower().endswith((".png", ".jpg", ".jpeg")):
                return export._rel(page, item["path"])
            return None
        return src

    author = people.get(row["author"], {})
    marks = {n["offset"]: (n["status"], n["length"]) for n in numbers}
    counts = {}
    for n in numbers:
        counts[n["status"]] = counts.get(n["status"], 0) + 1
    title = content.get("title") or post_id
    foreign = sorted({a["snapshot"] for a in artifacts.values() if a.get("snapshot")}
                     | {c["snapshot"] for c in claims.values() if c.get("snapshot")})
    body = (f"<p class=\"muted\">Write-up by {export.esc(author.get('name') or row['author'])} "
            f"({export.esc(author.get('kind'))}) · {export.esc(row['created'])} · "
            f"<span class=\"mono\">{export.esc(post_id)}</span></p>"
            "<p>Cite this preprint by its snapshot ID: the sha256 of <a href=\"snapshot.json\">snapshot.json</a> "
            "(also in <a href=\"snapshot.id\">snapshot.id</a>). Its claims are cited as "
            "<span class=\"mono\">snapshot:&lt;id&gt;/claim_…</span>.</p>"
            f"<p>Numbers: {len(numbers)} · " + " · ".join(f"{export.esc(k)} {v}" for k, v in sorted(counts.items()))
            + " · <a href=\"verification.html\">verification report</a> · run <span class=\"mono\">python3 verify.py</span> "
              "in this folder to re-check every hash and every number against the included bytes.</p>"
            + (f"<p class=\"muted\">Cites records of other snapshots: {', '.join(export.esc(s) for s in foreign)}.</p>"
               if foreign else "")
            + export.untrusted(author.get("name") or row["author"],
                               export.markdown_html(source, linker("index.html"), image("index.html"), numbers=marks,
                                                    figure_link=bytes_link("index.html")))
            + "<h2>Claims</h2><ul>" + "".join(f"<li><a href=\"claims.html#{export.esc(_key(c))}\">{export.esc(c)}</a></li>"
                                              for c in sorted(claims)) + "</ul>"
            + "<h2>Artifacts</h2><ul>" + "".join(
                f"<li><a href=\"{export.esc(page_of(a))}\">{export.esc(artifacts[a].get('title') or a)}</a> · "
                f"<a href=\"{export.esc(artifacts[a]['path'])}\">bytes</a> <span class=\"muted mono\">sha256 "
                f"{export.esc(artifacts[a]['sha256'])}</span></li>" for a in sorted(artifacts)) + "</ul>")
    site.page("index.html", title, body)

    claim_items = []
    for identity, claim in sorted(claims.items()):
        link = linker("claims.html")
        refs = "".join(f"<li>{export.esc(p.get('kind'))} " + (f"<a href=\"{export.esc(link(p['id']))}\">{export.esc(p['id'])}</a>"
                                                             if p.get("id") and link(p["id"]) else export.esc(p.get("id")))
                       + (f" <span class=\"mono\">#{export.esc(p['locator'])}</span>" if p.get("locator") else "") + "</li>"
                       for p in claim["pointers"])
        origin = (f"<p class=\"muted\">A claim of snapshot <span class=\"mono\">{export.esc(claim['snapshot'])}</span> "
                  "(foreign, untrusted).</p>" if claim.get("foreign") else "")
        claim_items.append(f"<li id=\"{export.esc(_key(identity))}\"><p class=\"mono\">{export.esc(identity)}</p>{origin}"
                           + export.untrusted("the claim's author", f"<p><strong>{export.esc(claim['status'])}</strong> "
                                                                    f"{export.esc(claim['text'])}</p>"
                                              + (f"<pre>{export.esc(json.dumps(claim['scope'], indent=1, sort_keys=True))}</pre>"
                                                 if claim["scope"] else ""))
                           + (f"<ul>{refs}</ul>" if refs else "") + "</li>")
    site.page("claims.html", "Cited claims", "<ul>" + "".join(claim_items) + "</ul>")

    for identity, item in sorted(artifacts.items()):
        page = page_of(identity)
        rel = export._rel(page, item["path"])
        origin = (f"<p class=\"band\">A record of snapshot <span class=\"mono\">{export.esc(item['snapshot'])}</span>, "
                  "included so this preprint verifies offline; foreign, untrusted data.</p>" if item.get("foreign") else "")
        manifest_link = (f"<dt>Manifest</dt><dd><a href=\"{export.esc(export._rel(page, item['manifest_path']))}\">manifest.json</a></dd>"
                         if item.get("manifest_path") else "")
        site.page(page, item.get("title") or identity,
                  f"<p class=\"mono\">{export.esc(identity)}</p>{origin}<dl><dt>Output bytes</dt><dd><a href=\"{export.esc(rel)}\">"
                  f"{export.esc(item['name'])}</a> · {item['bytes']} bytes · sha256 <span class=\"mono\">"
                  f"{export.esc(item['sha256'])}</span></dd>{manifest_link}<dt>Output role</dt><dd>"
                  f"{export.esc(item.get('output_role'))}</dd></dl>"
                  + (export.untrusted("the registering researcher", f"<p>{export.esc(item['summary'])}</p>")
                     if item.get("summary") else ""))

    rows = []
    for n in numbers:
        cells = []
        for p in n["pointers"]:
            target = artifacts.get(p["id"]) or claims.get(p["id"]) or {}
            where = (f"<a href=\"{export.esc(target['path'])}\">bytes</a> <span class=\"mono\">{export.esc(target['sha256'][:12])}…</span>"
                     if target.get("path") else f"<a href=\"claims.html#{export.esc(_key(p['id']))}\">claim</a>")
            found = p.get("found") or {}
            value = found.get("value") if isinstance(found, dict) else None
            cells.append(f"{export.esc(p['kind'])} <span class=\"mono\">{export.esc(p['id'][:24])}…"
                         + (f"#{export.esc(p['locator'])}" if p.get("locator") else "") + "</span> → "
                         + export.esc(p.get("result")) + (f" (found {export.esc(value)})" if value is not None else "")
                         + (f" ({export.esc(p['reason'])})" if p.get("reason") else "") + f" · {where}")
        rows.append(f"<tr><td>{n['line']}</td><td class=\"mono\">{export.esc(n['text'])}</td>"
                    f"<td class=\"num-{export.esc(n['status'])}\">{export.esc(n['status'])}</td>"
                    f"<td>{'<br>'.join(cells) or '<span class=muted>no pointer at the number</span>'}</td></tr>")
    site.page("verification.html", "Verification report",
              "<p>The commons' number checker verdict for every number in the write-up, the value it found in the "
              "cited record and a link to the bytes it read. This page is static: to re-check every hash and every "
              "value yourself, run <span class=\"mono\">python3 verify.py</span> in this folder (Python standard "
              "library only; it reads bytes and never executes anything from the folder).</p>"
              f"<p>Verdict: {export.esc(rendered['verdict']['source'])}, rules {export.esc(rendered['verdict']['rules'])}.</p>"
              "<table><thead><tr><th>Line</th><th>Number</th><th>Status</th><th>Pointers</th></tr></thead><tbody>"
              + "".join(rows) + "</tbody></table>", untrusted=False)

    site.add(f"source/{post_id}.md", source.encode("utf-8"))
    site.add(f"records/{post_id}.json", record_bytes)
    site.add(f"checks/{post_id}.json", canonical(export._check_record(view, post_id, row, set(artifacts))))
    site.add("records.json", canonical({
        "format": federation.RECORDS_FORMAT,
        "posts": [{"id": post_id, "title": title, "author": row["author"], "kind": content.get("kind"),
                   "created": row["created"]}],
        "claims": [{"id": c["id"], "post": c["post"], "text": c["text"], "status": c["status"], "scope": c["scope"],
                    "pointers": c["pointers"]} for c in claims.values() if not c.get("foreign")],
        "artifacts": [{"id": a["id"], "title": a.get("title"), "output_role": a.get("output_role"),
                       "derivation_key": a.get("derivation_key"), "manifest_path": a.get("manifest_path"),
                       "output": {"path": a["path"], "sha256": a["sha256"], "bytes": a["bytes"], "name": a["name"]}}
                      for a in artifacts.values() if not a.get("foreign")],
        "note": "Records of this preprint for federation indexes; records of other snapshots stay theirs."}))
    preprint = {"format": FORMAT, "rules": writeup.RULES_VERSION, "sequence": view.sequence(),
                "post": {"id": post_id, "title": title, "author": row["author"], "created": row["created"],
                         "body_blob": row["body_blob"]},
                "source": f"source/{post_id}.md", "record": f"records/{post_id}.json",
                "verdict": {k: rendered["verdict"].get(k) for k in ("source", "rules", "verdict_blob", "seq")
                            if rendered["verdict"].get(k) is not None},
                "numbers": numbers, "statuses": counts,
                "claims": {k: v for k, v in claims.items()}, "artifacts": {k: v for k, v in artifacts.items()},
                "posts": posts, "source_snapshots": foreign,
                "note": "Every number with its recorded checker result; verify.py recomputes each from the bytes listed "
                        "here. Offsets are Unicode code points into the Markdown source."}
    site.add("preprint.json", canonical(preprint))
    site.add("verify.py", VERIFIER.read_bytes())
    site.add("style.css", export.STYLE)
    manifest = {"format": export.FORMAT, "scope": {"kind": "preprint", "post": post_id},
                "counts": {"numbers": len(numbers), "claims": len(claims), "artifacts": len(artifacts),
                           "foreign_snapshots": len(foreign)},
                "moderation": [],
                "files": [{"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                          for path, data in sorted(site.files.items())],
                "note": "Content-addressed preprint: the snapshot ID is the sha256 of this file's bytes (canonical "
                        "JSON). Run verify.py to re-check every file and every number offline."}
    return site, manifest, {"numbers": len(numbers), "statuses": counts, "claims": len(claims),
                            "artifacts": len(artifacts), "foreign_snapshots": foreign}


def export_preprint(board, actor, post_id, output=None):
    """Write a preprint (permission `export`) and record a `preprint_exported` event. Without `output` it goes
    to `<commons>/exports/<snapshot id>/`."""
    person = require(board, board.agent(actor), "export")
    with Archive(board.root) as view:
        site, manifest, summary = build_preprint(view, post_id)
    if output is None:
        exports = Path(board.root) / "exports"
        staging = exports / f".staging-{uuid.uuid4().hex}"
        snapshot = export.write_site(site, manifest, staging)
        final = exports / snapshot
        if final.exists():
            shutil.rmtree(staging)
        else:
            staging.rename(final)
        output, relative = final, f"exports/{snapshot}"
    else:
        snapshot = export.write_site(site, manifest, output)
        relative = None
    total = sum(f["bytes"] for f in manifest["files"])
    with board.writer(), board.db:
        board.event("preprint_exported", {"snapshot": snapshot, "post": post_id, "actor": person["id"],
                                          "files": len(manifest["files"]), "bytes": total, "location": relative,
                                          **summary})
    return {"snapshot": snapshot, "post": post_id, "output": str(output), "location": relative,
            "files": len(manifest["files"]) + 1, "bytes": total, **summary,
            "verify": f"python3 {Path(output) / 'verify.py'} {output} --expect {snapshot}"}


def is_preprint(manifest):
    return isinstance(manifest.get("scope"), dict) and manifest["scope"].get("kind") == "preprint"
