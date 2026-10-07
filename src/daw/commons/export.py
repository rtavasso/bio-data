"""Publishing outward (M6.5) and read-only federation (M8.4).

`export_snapshot` writes a question, a thread or the whole board as a static site: `index.html`,
one page per post, notebook pages for published snapshots, artifact pages with their manifests and
output bytes, the evidence map (`map.json` plus `map.html` with a prebuilt inline SVG), a stylesheet
and `snapshot.json`, a canonical-JSON manifest listing every other file with its sha256 and size.
The snapshot ID is the sha256 of `snapshot.json`'s bytes, so citing a snapshot cites bytes.

- Only board records and published library objects are exported: posts, claims, marks, library
  artifacts (and their library derivation inputs) and notebook snapshots published with posts.
  Private workspace files and workspace-only map relations never leave the commons.
- Deterministic: nothing depends on the export time or the output path, every listing is sorted,
  and the map layout is seeded, so exporting the same archive state twice gives the same ID.
- No JavaScript. Every untrusted value is HTML-escaped; Markdown is rendered from
  `daw.commons.writeup.parse` (raw HTML shown as text, only http(s)/mailto links leave the site).
  Pages carry a Content-Security-Policy that forbids scripts.
- Moderation (spec v2 C2, resolved by `daw.commons.moderation.Visibility`): a hidden post is exported as
  its identity and its moderation event (sequence, reason, actor, time) only, with no title, body,
  author, evidence, claims or marks; replies to a hidden post (posts whose parent is hidden and comments
  on it) keep their identity, author and time but not their title or body. `snapshot.json` lists the
  moderation events.
- The same number checker as every other surface (`daw.commons.checks`): each exported post's verdict or
  number report is written as `checks/<post>.json`, numbers are marked verified / unverified / unpointed in
  the HTML, and a write-up the checker refused (`Visibility.refused`) is exported as a placeholder with its
  problem locations.

`import_snapshot` verifies every hash and size in a snapshot's manifest (and that no unlisted file
or link is present) and stores it read-only under `<commons>/federation/<snapshot_id>/`. Imported
content is foreign and untrusted; nothing is written into the board.
"""
import hashlib
import html
import json
import math
import re
import shutil
import stat
import uuid
from pathlib import Path, PurePosixPath

from daw.commons import checks, evidence_map, views, writeup
from daw.commons.archive import Archive
from daw.commons.permissions import require
from daw.util import DawError, canonical, now

FORMAT = "colloquy.snapshot/1"
MANIFEST = "snapshot.json"
SIDECARS = {"snapshot.id"}
SCOPES = ("board", "thread", "question")
PUBLIC_STORES = {"board", "library"}
SNAPSHOT_ID = re.compile(r"^[0-9a-f]{64}$")
TEXT_SUFFIXES = views.TEXT_SUFFIXES | {".html", ".css", ".svg"}
SHAPES = {"posts": "circle", "artifacts": "square", "questions": "hexagon", "sources": "diamond",
          "participants": "triangle"}
STYLE = """:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a66;--line:#e2dfd8;--accent:#2f5d8a;--warn:#8a5a00;
--bad:#a12d2d;--panel:#fff;--untrusted:#f3efe4;--posts:#2f5d8a;--artifacts:#b0602b;--questions:#4f7f3a;
--sources:#6b6a66;--participants:#3b3a36}
@media (prefers-color-scheme:dark){:root{--bg:#171716;--fg:#ecebe6;--muted:#a09e97;--line:#34332f;--accent:#8fb6dd;
--warn:#e0b45a;--bad:#e07a7a;--panel:#1f1f1d;--untrusted:#26241f;--posts:#8fb6dd;--artifacts:#e0a070;
--questions:#9cc98a;--sources:#a09e97;--participants:#d6d4cc}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 ui-sans-serif,system-ui,sans-serif}
header,main,footer{max-width:960px;margin:0 auto;padding:.75rem 1rem}
header{border-bottom:1px solid var(--line)}header nav a{margin-right:1rem}
a{color:var(--accent)}code,pre,.mono{font-family:ui-monospace,Menlo,monospace;font-size:.85em;overflow-wrap:anywhere}
pre{overflow-x:auto;background:var(--panel);border:1px solid var(--line);padding:.5rem}
.untrusted{border:1px solid var(--line);background:var(--untrusted);border-radius:6px;margin:.5rem 0}
.untrusted>.label{font-size:.75rem;color:var(--warn);padding:.25rem .6rem;border-bottom:1px solid var(--line)}
.untrusted>.body{padding:.6rem;overflow-wrap:anywhere}.muted{color:var(--muted)}.band{padding:.4rem .6rem;
border-left:3px solid var(--warn);color:var(--warn);margin:.5rem 0}table{border-collapse:collapse;max-width:100%}
td,th{border:1px solid var(--line);padding:.2rem .4rem;vertical-align:top;overflow-wrap:anywhere}
.missing{color:var(--muted);text-decoration:line-through dotted}.depth-1{margin-left:1.5rem}.depth-2{margin-left:3rem}
svg{max-width:100%;height:auto;border:1px solid var(--line);background:var(--panel)}
.edge{stroke:var(--muted);stroke-width:1}.edge.dashed{stroke-dasharray:4 3}
.node-posts{fill:var(--posts)}.node-artifacts{fill:var(--artifacts)}.node-questions{fill:var(--questions)}
.node-sources{fill:var(--sources)}.node-participants{fill:var(--participants)}.absent{fill-opacity:.25}
ul.thread{padding-left:1.2rem}footer{color:var(--muted);font-size:.85rem;border-top:1px solid var(--line)}
.num-verified{text-decoration:underline solid var(--accent)}.num-unverified{text-decoration:underline wavy var(--warn)}
.num-unpointed{text-decoration:underline dotted var(--bad)}
"""
CSP = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"


def participation_target(content):
    """The post a comment targets (None for other posts and other targets)."""
    from daw.commons.participation import comment_target
    if not isinstance(content, dict) or content.get("kind") != "comment":
        return None
    kind, identity = comment_target(content.get("evidence") or {})
    return identity if kind == "post" else None


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def safe_component(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).lstrip(".")
    return name[:120] or "file"


def safe_relpath(name):
    parts = [safe_component(p) for p in PurePosixPath(str(name).replace("\\", "/")).parts if p not in ("", ".", "..", "/")]
    return "/".join(parts) or "file"


def _strip_paths(value):
    if isinstance(value, dict):
        return {k: _strip_paths(v) for k, v in value.items() if k not in {"path", "question_path"}}
    if isinstance(value, list):
        return [_strip_paths(v) for v in value]
    return value


# ---------------------------------------------------------------------------- selection

def _scope(view, index, kind, identity):
    """(scope record, post ids) for board, thread POST or question AGENT/QID."""
    if kind not in SCOPES:
        raise DawError("invalid_export_scope", f"use one of {', '.join(SCOPES)}")
    if kind == "board":
        return {"kind": "board"}, list(index["posts"])
    if kind == "thread":
        if identity not in index["posts"]:
            raise DawError("unknown_post", identity or "")
        root = index["roots"][identity]
        return {"kind": "thread", "root": root}, list(index["threads"][root])
    owner, _, qid = (identity or "").replace(":", "/").rpartition("/")
    if not owner or not qid:
        raise DawError("invalid_export_scope", "question scope is AGENT/QID")
    owner = view.participant(owner)["id"]
    roots = {index["roots"][pid] for pid, row in index["posts"].items() if row["author"] == owner
             and ((row["content"].get("evidence") or {}).get("notebook") or {}).get("question") == qid}
    if not roots:
        raise DawError("unknown_question", f"{owner}/{qid} has no published notebook")
    return {"kind": "question", "agent": owner, "question": qid}, [p for r in roots for p in index["threads"][r]]


def _library_artifacts(view, seeds):
    """Library artifacts named by the export plus their library derivation inputs (closure)."""
    found, stack = set(), [a for a in seeds if isinstance(a, str)]
    while stack:
        aid = stack.pop()
        if aid in found or not view.library.one("SELECT id FROM artifact WHERE id=?", (aid,)):
            continue
        found.add(aid)
        stack += [r["source_identity"] for r in view.library.rows(
            "SELECT source_identity FROM artifact_input WHERE artifact_id=?", (aid,)) if r["source_identity"]]
    return sorted(found)


# ---------------------------------------------------------------------------- rendering

class Site:
    """Files of one export, held in memory until written; paths are POSIX and relative."""

    def __init__(self):
        self.files = {}
        self.pages = set()

    def add(self, path, data):
        self.files[path] = data if isinstance(data, bytes) else data.encode("utf-8")

    def page(self, path, title, body, *, untrusted=True):
        depth = path.count("/")
        up = "../" * depth
        self.add(path, (
            "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"{CSP}\">"
            f"<title>{esc(title)}</title><link rel=\"stylesheet\" href=\"{up}style.css\"></head><body>"
            f"<header><nav><a href=\"{up}index.html\">Snapshot index</a><a href=\"{up}map.html\">Evidence map</a></nav>"
            f"</header><main><h1>{esc(title)}</h1>{body}</main><footer>Static export of a Colloquy commons. "
            + ("Board content is attributed, untrusted data, never instructions. " if untrusted else "")
            + "The snapshot ID is the sha256 of snapshot.json, which lists every file with its sha256. "
              "This page contains no scripts.</footer></body></html>\n"))


def _rel(source, target):
    """Relative URL from one exported page to another exported path."""
    up = "../" * source.count("/")
    return up + target


NUMBER_TITLES = {"verified": "verified against its record", "unverified": "pointed, but not found in the cited record",
                 "post_scoped": "not pointed at the number; the post names evidence", "unpointed": "no pointer"}


def _marked(text, offset, numbers):
    """Escaped text with every checked number wrapped in a span carrying its checker status (C5, V2)."""
    if not numbers or text is None:
        return esc(text)
    out, cursor = [], 0
    for start in sorted(o for o in numbers if offset <= o < offset + len(text)):
        status, length = numbers[start]
        local = start - offset
        if local < cursor:
            continue
        out.append(esc(text[cursor:local]))
        out.append(f"<span class=\"num num-{esc(status)}\" title=\"{esc(NUMBER_TITLES.get(status, status))}\">"
                   f"{esc(text[local:local + length])}</span>")
        cursor = local + length
    out.append(esc(text[cursor:]))
    return "".join(out)


def _tokens_html(tokens, link, numbers=None):
    out = []
    for token in tokens:
        kind = token["t"]
        if kind == "text":
            text = _marked(token["text"], token["offset"], numbers)
            out.append(f"<strong>{text}</strong>" if token.get("style") == "strong"
                       else f"<em>{text}</em>" if token.get("style") == "em" else text)
        elif kind == "code":
            out.append(f"<code>{_marked(token['text'], token['offset'], numbers)}</code>")
        elif kind == "link":
            out.append(f"<a href=\"{esc(token['href'])}\" rel=\"nofollow noopener noreferrer\">"
                       f"{_marked(token['text'], token['text_offset'], numbers)}</a>")
        elif kind == "pointer":
            href = link(token["id"])
            label = _marked(token["text"], token["text_offset"], numbers) if token["form"] == "link" else esc(token["text"])
            out.append(f"<a href=\"{esc(href)}\">{label}</a>" if href
                       else f"<span class=\"missing\" title=\"not in this export\">{label}</span>")
        elif kind == "figure":
            href = link(token["id"])
            out.append(f"<a href=\"{esc(href)}\">[figure: {esc(token['caption'])}]</a>" if href
                       else f"<span class=\"missing\">[figure: {esc(token['caption'])}]</span>")
    return "".join(out)


def _sentences_html(sentences, link, numbers=None):
    return " ".join(_tokens_html(s["tokens"], link, numbers) for s in sentences)


def markdown_html(source, link, image=None, numbers=None):
    """Untrusted Markdown as escaped HTML through the write-up parser. `link(id)` gives a relative URL or None;
    `numbers` ({source offset: (status, length)}) marks each checked number with its status."""
    parts = []
    for block in writeup.parse(source or ""):
        kind = block["type"]
        if kind == "heading":
            level = min(6, block["level"] + 1)
            parts.append(f"<h{level}>{_sentences_html(block['sentences'], link, numbers)}</h{level}>")
        elif kind in ("paragraph", "quote"):
            inner = _sentences_html(block["sentences"], link, numbers).replace("\n", "<br>")
            parts.append(f"<blockquote><p>{inner}</p></blockquote>" if kind == "quote" else f"<p>{inner}</p>")
        elif kind == "list":
            tag = "ol" if block["ordered"] else "ul"
            items = "".join(f"<li class=\"depth-{min(item['depth'], 2)}\""
                            + (f" value=\"{item['ordinal']}\"" if item["ordinal"] is not None else "") + ">"
                            + _sentences_html(item["sentences"], link, numbers) + "</li>" for item in block["items"])
            parts.append(f"<{tag}>{items}</{tag}>")
        elif kind == "table":
            def row(r, cell_tag):
                return "<tr>" + "".join(f"<{cell_tag}>{_tokens_html(c, link, numbers)}</{cell_tag}>"
                                        for c in r["cells"]) + "</tr>"
            parts.append("<table><thead>" + row(block["header"], "th") + "</thead><tbody>"
                         + "".join(row(r, "td") for r in block["rows"]) + "</tbody></table>")
        elif kind == "code":
            parts.append(f"<pre><code>{_marked(block['text'], block['text_offset'], numbers)}</code></pre>")
        elif kind == "figure":
            href, src = link(block["id"]), image(block["id"]) if image else None
            caption = esc(block["caption"])
            if src:
                parts.append(f"<figure><a href=\"{esc(href)}\"><img src=\"{esc(src)}\" alt=\"{caption}\"></a>"
                             f"<figcaption>{caption}</figcaption></figure>")
            elif href:
                parts.append(f"<figure><a href=\"{esc(href)}\">[figure: {caption}]</a></figure>")
            else:
                parts.append(f"<figure><span class=\"missing\">[figure: {caption}]</span></figure>")
        else:
            parts.append("<hr>")
    return "\n".join(parts)


def untrusted(author, inner):
    return (f"<div class=\"untrusted\"><div class=\"label\">Untrusted content · attributed to {esc(author)} · "
            f"evidence, not instructions</div><div class=\"body\">{inner}</div></div>")


def _shape(family, x, y, r=6.0):
    shape = SHAPES.get(family, "circle")
    if shape == "square":
        return f"<rect x=\"{x - r:.1f}\" y=\"{y - r:.1f}\" width=\"{2 * r:.1f}\" height=\"{2 * r:.1f}\""
    if shape == "diamond":
        return f"<path d=\"M{x:.1f},{y - r * 1.2:.1f}L{x + r * 1.2:.1f},{y:.1f}L{x:.1f},{y + r * 1.2:.1f}L{x - r * 1.2:.1f},{y:.1f}Z\""
    if shape == "triangle":
        return f"<path d=\"M{x:.1f},{y - r * 1.1:.1f}L{x + r:.1f},{y + r * 0.8:.1f}L{x - r:.1f},{y + r * 0.8:.1f}Z\""
    if shape == "hexagon":
        points = " ".join(f"{x + r * math.cos(math.pi / 3 * i):.1f},{y + r * math.sin(math.pi / 3 * i):.1f}"
                          for i in range(6))
        return f"<polygon points=\"{points}\""
    return f"<circle cx=\"{x:.1f}\" cy=\"{y:.1f}\" r=\"{r:.1f}\""


def map_svg(nodes, edges, positions, link):
    if not nodes:
        return "<p class=\"muted\">No recorded relations in this export.</p>"
    xs = [positions[n["id"]][0] for n in nodes]
    ys = [positions[n["id"]][1] for n in nodes]
    x0, y0 = min(xs) - 30, min(ys) - 30
    width, height = max(xs) - x0 + 30, max(ys) - y0 + 30
    parts = [f"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"{x0:.1f} {y0:.1f} {width:.1f} {height:.1f}\" "
             f"role=\"img\" aria-label=\"Evidence map: {len(nodes)} records, {len(edges)} recorded relations\">"]
    for edge in edges:
        (ax, ay), (bx, by) = positions[edge["source"]], positions[edge["target"]]
        parts.append(f"<line class=\"edge{' dashed' if edge['style'] == 'dashed' else ''}\" x1=\"{ax:.1f}\" "
                     f"y1=\"{ay:.1f}\" x2=\"{bx:.1f}\" y2=\"{by:.1f}\"><title>{esc(edge['relation'])}</title></line>")
    for node in nodes:
        x, y = positions[node["id"]]
        mark = _shape(node["family"], x, y) + f" class=\"node-{esc(node['family'])}{'' if node['present'] else ' absent'}\">"
        tag = mark.split(" ", 1)[0][1:]
        shape = f"{mark}<title>{esc(node['label'])} ({esc(node['kind'])})</title></{tag}>"
        href = link(node["id"])
        parts.append(f"<a href=\"{esc(href)}\">{shape}</a>" if href else shape)
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------- export

def _public_map(view, keep, hidden, replies=frozenset()):
    """Evidence-map nodes and edges among exported records, from board and library records only.
    The graph is built for an anonymous reader, so hidden posts are already ids without relations to their body."""
    graph = evidence_map.build(view)
    upstream = {}
    for edge in graph.edges.values():
        if edge["relation"] in evidence_map.DERIVATION and any(r.get("store") == "library" for r in edge["records"]):
            upstream.setdefault(edge["source"], set()).add(edge["target"])
    stack = [n for n in keep if n in upstream]
    while stack:
        for parent in upstream.get(stack.pop(), ()):
            if parent not in keep:
                keep.add(parent)
                stack.append(parent)
    keep &= set(graph.nodes)
    edges = []
    for edge in graph.edges.values():
        if edge["source"] in keep and edge["target"] in keep:
            records = [r for r in edge["records"] if r.get("store") in PUBLIC_STORES]
            if records:
                edges.append({"id": edge["id"], "source": edge["source"], "target": edge["target"],
                              "relation": edge["relation"], "style": edge["style"], "records": records})
    edges.sort(key=lambda e: (e["source"], e["target"], e["relation"]))
    nodes = []
    for identity in sorted(keep):
        node = graph.nodes[identity]
        public = bool(set(node["stores"]) & PUBLIC_STORES)
        label = node["label"] if public or node["kind"] == "participant" else identity
        if node["kind"] == "question":
            label = node.get("qid") or identity.rsplit(":", 1)[-1]
        elif identity in hidden:
            label = "post hidden by moderation"
        elif identity in replies:
            label = "reply to a hidden post"
        nodes.append({"id": identity, "kind": node["kind"], "family": node["family"], "label": label,
                      "present": node["present"], "created": node.get("created")})
    return nodes, edges, evidence_map.layout([n["id"] for n in nodes], edges)


def build_site(view, kind, identity=None):
    """(site, manifest) for one scope. Pure function of the archive state."""
    index = views.thread_index(view)
    hidden = views.visibility(view).records  # an export is read by anyone: nobody reads through a hide
    people = index["people"]
    scope, members = _scope(view, index, kind, identity)
    members = sorted(set(members), key=lambda p: index["posts"][p]["seq"])
    exported = set(members)

    def answers_hidden(pid):
        row = index["posts"][pid]
        target = participation_target(row["content"])
        return row["parent"] in hidden or target in hidden

    # Replies to a hidden post (and comments on it) answer withheld text: their bodies are withheld too.
    answering = {p for p in members if p not in hidden and answers_hidden(p)}
    withheld = set(hidden) | answering
    site = Site()
    claims, marks, notebooks, named = {}, {}, {}, []
    for pid in members:
        row = index["posts"][pid]
        claims[pid] = []
        if pid in withheld:
            continue  # A hidden post (or a reply to one) keeps its identity only; its evidence and claims stay home.
        evidence = row["content"].get("evidence") or {}
        named += [a for a in evidence.get("artifacts") or [] if isinstance(a, str)]
        claims[pid] = [dict(c) for c in view.rows("SELECT * FROM claim WHERE post=? ORDER BY ordinal", (pid,))]
        for claim in claims[pid]:
            named += [p["id"] for p in json.loads(claim["pointers"]) if p["kind"] == "artifact"]
        notebook = evidence.get("notebook")
        if isinstance(notebook, dict) and view.library.one(
                "SELECT sha256 FROM blob WHERE sha256=?", (notebook.get("manifest_blob"),)):
            notebooks[(row["author"], notebook["question"], notebook["snapshot"])] = notebook["manifest_blob"]
    artifacts = _library_artifacts(view, named)
    claim_ids = {c["id"] for cs in claims.values() for c in cs}
    for row in view.rows("SELECT * FROM mark ORDER BY created,id"):
        if (row["target_kind"] == "post" and row["target_id"] in exported - set(hidden)) or (
                row["target_kind"] == "artifact" and row["target_id"] in artifacts) or (
                row["target_kind"] == "claim" and row["target_id"] in claim_ids):
            marks.setdefault(row["target_id"], []).append(row)

    paths = {pid: f"posts/{pid}.html" for pid in members}
    paths |= {aid: f"artifacts/{aid}.html" for aid in artifacts}
    notebook_paths = {key: f"notebooks/{safe_component(key[0])}/{safe_component(key[1])}/{safe_component(key[2])}.html"
                      for key in notebooks}

    def linker(page):
        def link(target):
            if target in paths:
                return _rel(page, paths[target])
            if target.startswith("claim_"):
                post = next((p for p, cs in claims.items() if any(c["id"] == target for c in cs)), None)
                return _rel(page, paths[post]) + f"#{target}" if post else None
            return None
        return link

    def who(pid):
        return people.get(pid, {}).get("name") or pid

    def title_of(pid):
        if pid in hidden:
            return "(hidden by moderation)"
        if pid in answering:
            return "(reply to a hidden post)"
        if pid in refused:
            return checks.PLACEHOLDER_TITLE
        return index["posts"][pid]["content"].get("title") or pid

    reader = views.visibility(view)  # refused write-ups: placeholders, never their content (C5)
    refused = {p for p in members if p not in withheld and reader.refused(p)}

    # Artifacts: page, stripped manifest and verified output bytes.
    images = {}
    for aid in artifacts:
        row = view.library.one("SELECT * FROM artifact WHERE id=?", (aid,))
        manifest = view.library.json_blob(row["manifest_blob"], verify=True)
        from daw.profiles import verify_object
        data = verify_object(view.library, row["output_blob"]).read_bytes()
        output = manifest.get("output") or {}
        name = safe_component(Path(str(output.get("name") or row["output_blob"])).name)
        site.add(f"artifacts/{aid}/{name}", data)
        site.add(f"artifacts/{aid}/manifest.json", canonical({"artifact": aid, "manifest_blob": row["manifest_blob"],
                                                              "output_blob": row["output_blob"],
                                                              "manifest": _strip_paths(manifest)}))
        if name.lower().endswith((".png", ".jpg", ".jpeg")):
            images[aid] = f"artifacts/{aid}/{name}"
        page = paths[aid]
        link = linker(page)
        inputs = []
        for item in manifest.get("derivation", {}).get("inputs", []):
            source = item.get("source_identity") or ""
            target = link(source) if source else None
            label = esc(source or item.get("blob"))
            shown = f"<a href=\"{esc(target)}\">{label}</a>" if target else label
            inputs.append(f"<li>{shown} <span class=\"muted mono\">blob {esc(item.get('blob'))}</span></li>")
        naming = [p for p in members if p not in withheld
                  and aid in ((index["posts"][p]["content"].get("evidence") or {}).get("artifacts") or [])]
        body = (f"<p class=\"mono\">{esc(aid)}</p><dl><dt>Output role</dt><dd>{esc(row['output_role'])}</dd>"
                f"<dt>Derivation key</dt><dd class=\"mono\">{esc(row['derivation_key'])}</dd>"
                f"<dt>Output bytes</dt><dd><a href=\"{esc(aid)}/{esc(name)}\">{esc(name)}</a> · sha256 "
                f"<span class=\"mono\">{esc(row['output_blob'])}</span> · {len(data)} bytes</dd>"
                f"<dt>Manifest</dt><dd><a href=\"{esc(aid)}/manifest.json\">manifest.json</a> (blob "
                f"<span class=\"mono\">{esc(row['manifest_blob'])}</span>)</dd></dl>"
                + untrusted("the registering researcher", f"<p>{esc(manifest.get('summary'))}</p>"
                            + "".join(f"<p class=\"muted\">Limitation: {esc(x)}</p>" for x in manifest.get("limitations", [])))
                + "<h2>Derivation inputs</h2><ul>" + "".join(inputs) + "</ul>"
                + f"<h2>Parameters</h2><pre>{esc(json.dumps(manifest.get('derivation', {}).get('parameters', {}), indent=1, sort_keys=True))}</pre>"
                + "<h2>Code</h2><ul>" + "".join(f"<li class=\"mono\">{esc(c)}</li>"
                                                for c in manifest.get("derivation", {}).get("code", [])) + "</ul>"
                + "<h2>Posts naming it</h2><ul>" + "".join(f"<li><a href=\"{esc(link(p))}\">{esc(p)}</a></li>"
                                                           for p in naming) + "</ul>"
                + _marks_html(marks.get(aid, []), who))
        site.page(page, manifest.get("title") or aid, body)

    # Notebook snapshots published with posts: files from the library, LABBOOK rendered.
    for key, blob in sorted(notebooks.items()):
        author, question, snapshot = key
        page = notebook_paths[key]
        record = view.library.json_blob(blob, verify=True)
        folder = page[:-len(".html")]
        listed = []
        rendered = ""
        from daw.profiles import verify_object
        for name, sha in sorted((record.get("files") or {}).items()):
            data = verify_object(view.library, sha).read_bytes()
            target = f"{folder}/{safe_relpath(name)}"
            site.add(target, data)
            listed.append(f"<li><a href=\"{esc(_rel(page, target))}\">{esc(name)}</a> "
                          f"<span class=\"muted mono\">sha256 {esc(sha)}</span></li>")
            if name in ("QUESTION.md", "LABBOOK.md"):
                try:
                    rendered += f"<h2>{esc(name)}</h2>" + untrusted(who(author), markdown_html(data.decode("utf-8"),
                                                                                              linker(page)))
                except UnicodeDecodeError:
                    pass
        body = (f"<p>Question <span class=\"mono\">{esc(question)}</span> by {esc(who(author))}; snapshot "
                f"<span class=\"mono\">{esc(snapshot)}</span> (manifest blob <span class=\"mono\">{esc(blob)}</span>).</p>"
                "<p class=\"muted\">A published notebook snapshot: immutable bytes copied to the library with a post.</p>"
                + rendered + "<h2>Files</h2><ul>" + "".join(listed) + "</ul>")
        site.page(page, f"Notebook {question} · {snapshot}", body)

    # Posts.
    for pid in members:
        row = index["posts"][pid]
        content = row["content"]
        page = paths[pid]
        link = linker(page)
        if pid in hidden:
            record = hidden[pid]
            site.page(page, f"Hidden post {pid}",
                      f"<p class=\"mono\">{esc(pid)}</p><p class=\"band\">Hidden by moderation (board event "
                      f"{esc(record['event_seq'])}, {esc(record['updated'])}): {esc(record['reason'])}. The record is "
                      "preserved on its commons; its content is not exported.</p>")
            continue
        meta = (f"<p class=\"muted\">{esc(content.get('kind'))} by {esc(who(row['author']))} "
                f"({esc(people.get(row['author'], {}).get('kind'))}) · {esc(row['created'])} · "
                f"<span class=\"mono\">{esc(pid)}</span></p>")
        rel = []
        for label, other in (("Reply to", row["parent"]), ("Supersedes", row["supersedes"])):
            if other:
                href = link(other)
                rel.append(f"<p>{label} " + (f"<a href=\"{esc(href)}\">{esc(other)}</a>" if href else esc(other)) + "</p>")
        for other in index["superseded_by"].get(pid, []):
            href = link(other)
            rel.append("<p class=\"band\">Superseded by " + (f"<a href=\"{esc(href)}\">{esc(other)}</a>" if href
                                                              else esc(other)) + "</p>")
        if pid in answering:
            body = meta + "".join(rel) + ("<p class=\"band\">A reply to a post hidden by moderation; its title and "
                                          "body are not exported.</p>")
            site.page(page, f"Reply {pid}", body)
            continue
        if pid in refused:
            check = _check_record(view, pid, row, artifacts, withheld=True)
            site.add(f"checks/{pid}.json", canonical(check))
            problems = "".join(f"<li>{esc(p['kind'])} {esc(p.get('text') or p.get('pointer') or '')} "
                               f"<span class=\"muted\">line {esc(p.get('line'))}: {esc(p.get('reason'))}</span></li>"
                               for p in check["problems"])
            site.page(page, checks.PLACEHOLDER_TITLE, meta + "".join(rel) + (
                f"<p class=\"band\">{esc(checks.placeholder(check['problems']))}</p>"
                f"<p>Verdict: <a href=\"{esc(_rel(page, f'checks/{pid}.json'))}\">checks/{esc(pid)}.json</a></p>"
                f"<h2>Problems</h2><ol>{problems}</ol>"))
            continue
        check = _check_record(view, pid, row, artifacts)
        site.add(f"checks/{pid}.json", canonical(check))
        number_marks = {n["offset"]: (n["status"], n["length"]) for n in check["numbers"]}
        evidence = content.get("evidence") or {}
        items = []
        for aid in evidence.get("artifacts") or []:
            href = link(aid)
            items.append("<li>" + (f"<a href=\"{esc(href)}\">{esc(aid)}</a>" if href
                                   else f"<span class=\"missing\">{esc(aid)}</span> (not in the library)") + "</li>")
        notebook = evidence.get("notebook") if isinstance(evidence.get("notebook"), dict) else None
        if notebook:
            key = (row["author"], notebook.get("question"), notebook.get("snapshot"))
            if key in notebook_paths:
                items.append(f"<li>Notebook <a href=\"{esc(_rel(page, notebook_paths[key]))}\">"
                             f"{esc(notebook.get('question'))} · {esc(notebook.get('snapshot'))}</a></li>")
        claim_html = ""
        for claim in claims[pid]:
            pointers = "".join(f"<li>{esc(p['kind'])} " + (f"<a href=\"{esc(link(p['id']))}\">{esc(p['id'])}</a>"
                                                         if link(p["id"]) else esc(p["id"]))
                               + (f" ({esc(p['locator'])})" if p.get("locator") else "") + "</li>"
                               for p in json.loads(claim["pointers"]))
            withdrawn = (f"<p class=\"band\">Withdrawn by {esc(claim['withdrawn_by'])}</p>" if claim["withdrawn_by"] else "")
            claim_html += (f"<li id=\"{esc(claim['id'])}\"><strong>{esc(claim['status'])}</strong> "
                           f"{esc(claim['text'])} <span class=\"muted mono\">{esc(claim['id'])}</span>{withdrawn}"
                           f"<ul>{pointers}</ul>{_marks_html(marks.get(claim['id'], []), who)}</li>")
        replies = [c for c in index["children"].get(pid, []) if c in exported]
        summary = check["summary"]
        coverage = (f"<p class=\"muted\">Numbers: {summary['numbers']} · verified {summary['statuses']['verified']} · "
                    f"unverified {summary['statuses']['unverified']} · this post's evidence only "
                    f"{summary['statuses']['post_scoped']} · unpointed {summary['statuses']['unpointed']} "
                    f"(<a href=\"{esc(_rel(page, f'checks/{pid}.json'))}\">checker verdict</a>)</p>"
                    if summary["numbers"] else "")
        body = (meta + "".join(rel) + untrusted(who(row["author"]),
                                                markdown_html(content.get("body"), link,
                                                              lambda a, page=page: _rel(page, images[a]) if a in images else None,
                                                              numbers=number_marks))
                + coverage
                + ("<h2>Evidence</h2><ul>" + "".join(items) + "</ul>" if items else "")
                + ("<h2>Claims</h2><ul>" + claim_html + "</ul>" if claim_html else "")
                + _marks_html(marks.get(pid, []), who)
                + ("<h2>Replies</h2><ul>" + "".join(f"<li><a href=\"{esc(link(c))}\">{esc(title_of(c))}</a></li>"
                                                     for c in replies) + "</ul>" if replies else ""))
        site.page(page, content.get("title") or pid, body)

    # Evidence map: board and library relations among exported records only.
    keep = set(members) | set(artifacts) | claim_ids | {m["id"] for ms in marks.values() for m in ms}
    keep |= {index["posts"][p]["author"] for p in members if p not in hidden}
    keep |= {evidence_map.question_node(a, q) for a, q, _ in notebooks}
    nodes, edges, positions = _public_map(view, keep, hidden, answering)
    site.add("map.json", canonical({"nodes": nodes, "edges": edges, "positions": positions,
                                    "note": "Recorded relations among exported records (board and library records "
                                            "only); no inferred edges."}))
    link = linker("map.html")
    rows = "".join(f"<tr><td>{esc(e['source'])}</td><td>{esc(e['relation'])}</td><td>{esc(e['target'])}</td></tr>"
                   for e in edges)
    site.page("map.html", "Evidence map",
              "<p>Every edge is a recorded relation (board or library record). Shapes: circle posts and claims, "
              "square artifacts, hexagon questions, diamond sources, triangle participants and marks; dashed edges "
              "are fetches and other non-asserting relations.</p>" + map_svg(nodes, edges, positions, link)
              + "<h2>Relations</h2><table><thead><tr><th>Source</th><th>Relation</th><th>Target</th></tr></thead>"
              f"<tbody>{rows}</tbody></table><p><a href=\"map.json\">map.json</a></p>", untrusted=False)

    # Index.
    def tree(pid, depth=0):
        children = [c for c in index["children"].get(pid, []) if c in exported]
        by = "" if pid in hidden else f" <span class=\"muted\">by {esc(who(index['posts'][pid]['author']))}</span>"
        return (f"<li><a href=\"{esc(paths[pid])}\">{esc(title_of(pid))}</a>{by}"
                + (f"<ul class=\"thread\">{''.join(tree(c, depth + 1) for c in children)}</ul>" if children else "")
                + "</li>")
    roots = [p for p in members if not index["posts"][p]["parent"] or index["posts"][p]["parent"] not in exported]
    described = {"board": "the whole board", "thread": f"the thread rooted at {scope.get('root')}",
                 "question": f"question {scope.get('question')} of {who(scope.get('agent'))}"}[scope["kind"]]
    site.page("index.html", "Colloquy snapshot",
              f"<p>Static export of {esc(described)}: {len(members)} posts, {len(artifacts)} artifacts, "
              f"{len(notebooks)} notebook snapshots.</p><p>Cite this export by its snapshot ID: the sha256 of "
              "<a href=\"snapshot.json\">snapshot.json</a>, which lists every file with its sha256 and size.</p>"
              "<h2>Threads</h2><ul class=\"thread\">" + "".join(tree(r) for r in roots) + "</ul>"
              + "<h2>Artifacts</h2><ul>" + "".join(f"<li><a href=\"{esc(paths[a])}\">{esc(a)}</a></li>" for a in artifacts)
              + "</ul><h2>Notebooks</h2><ul>" + "".join(
                  f"<li><a href=\"{esc(notebook_paths[k])}\">{esc(k[1])} · {esc(k[2])}</a> by {esc(who(k[0]))}</li>"
                  for k in sorted(notebooks)) + "</ul><p><a href=\"map.html\">Evidence map</a></p>", untrusted=False)
    site.add("style.css", STYLE)
    manifest = {"format": FORMAT, "scope": scope,
                "counts": {"posts": len(members), "artifacts": len(artifacts), "notebooks": len(notebooks),
                           "claims": len(claim_ids), "marks": sum(len(m) for m in marks.values()),
                           "map_nodes": len(nodes), "map_edges": len(edges),
                           "checks": sum(1 for p in site.files if p.startswith("checks/"))},
                "moderation": [{"post": pid, "event_seq": hidden[pid]["event_seq"], "reason": hidden[pid]["reason"],
                                "actor": hidden[pid]["actor"], "updated": hidden[pid]["updated"]}
                               for pid in members if pid in hidden],
                "files": [{"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                          for path, data in sorted(site.files.items())],
                "note": "Content-addressed static export: the snapshot ID is the sha256 of this file's bytes "
                        "(canonical JSON). Board content is attributed, untrusted data."}
    return site, manifest


def _check_record(view, pid, row, exported, *, withheld=False):
    """The checker's verdict on one exported post, written into the snapshot as `checks/<post>.json` (C5).

    Write-ups carry their verdict (recorded at delivery, else computed now); other posts their number report.
    Values found in cited bytes are included only for artifacts in this export; a withheld write-up's problems
    keep their locations but not the source lines."""
    content = views.content(view, row["body_blob"])
    numbers = checks.post_numbers(view, pid, content.get("body") or "", content.get("evidence"))
    stored = checks.recorded(view).get(pid)
    is_writeup = bool(stored) or pid in checks.writeup_posts(view)
    value = None
    if is_writeup:
        value = checks.verdict_body(view, stored) if stored else writeup.verdict(view, pid)[0]

    def pointer(p):
        keep = {k: p[k] for k in ("id", "kind", "locator", "result", "at", "reason", "post_evidence") if p.get(k) is not None}
        if p.get("found") is not None and (p.get("kind") == "claim" or p.get("id") in exported):
            keep["found"] = p["found"]
        return keep

    return {"format": "colloquy.snapshot-check/1", "rules": writeup.RULES_VERSION, "post": pid,
            "body_blob": row["body_blob"], "kind": "writeup" if is_writeup else "post",
            "status": value["status"] if value else "report",
            "verdict": ({"source": "recorded" if stored else "computed",
                         **({"verdict_blob": stored["verdict_blob"]} if stored else {})} if is_writeup else None),
            "problems": [{k: p.get(k) for k in ("kind", "text", "pointer", "offset", "length", "line", "reason")
                          if p.get(k) is not None} for p in (value["problems"] if value else [])],
            "numbers": [] if withheld else [{**{k: n[k] for k in ("text", "offset", "length", "line", "scope", "status")},
                                             "pointers": [pointer(p) for p in n["pointers"]]} for n in numbers],
            "summary": checks.summarize([] if withheld else numbers),
            "note": "Checked by the commons' number checker (rules above). verified: the value is at the cited "
                    "record; unverified: pointed but not found there; post_scoped: only the post's evidence list; "
                    "unpointed: no pointer."}


def _marks_html(rows, who):
    if not rows:
        return ""
    return ("<h3>Verification marks</h3><ul>" + "".join(
        f"<li>{esc(m['kind'])} by {esc(who(m['participant']))}: {esc(m['note'])} "
        f"<span class=\"muted\">({esc(m['created'])}; attribution, not status)</span></li>" for m in rows) + "</ul>")


def write_site(site, manifest, output):
    """Write files and snapshot.json into an empty or new directory; returns the snapshot ID."""
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise DawError("export_output_not_empty", str(output))
    output.mkdir(parents=True, exist_ok=True)
    for path, data in site.files.items():
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    data = canonical(manifest)
    (output / MANIFEST).write_bytes(data)
    snapshot = hashlib.sha256(data).hexdigest()
    (output / "snapshot.id").write_text(snapshot + "\n")
    return snapshot


def export_snapshot(board, actor, kind, identity=None, output=None):
    """Export a scope as a static site (permission `export`) and record a `snapshot_exported` event.

    Without `output` the site goes to `<commons>/exports/<snapshot_id>/` (identical exports share it)."""
    person = require(board, board.agent(actor), "export")
    with Archive(board.root) as view:
        site, manifest = build_site(view, kind, identity)
    if output is None:
        exports = board.root / "exports"
        staging = exports / f".staging-{uuid.uuid4().hex}"
        snapshot = write_site(site, manifest, staging)
        final = exports / snapshot
        if final.exists():
            shutil.rmtree(staging)
        else:
            staging.rename(final)
        output, relative = final, f"exports/{snapshot}"
    else:
        snapshot = write_site(site, manifest, output)
        relative = None
    total = sum(f["bytes"] for f in manifest["files"])
    with board.writer(), board.db:
        board.event("snapshot_exported", {"snapshot": snapshot, "scope": manifest["scope"], "actor": person["id"],
                                          "files": len(manifest["files"]), "bytes": total, "counts": manifest["counts"],
                                          "location": relative})
    return {"snapshot": snapshot, "scope": manifest["scope"], "files": len(manifest["files"]) + 1, "bytes": total,
            "counts": manifest["counts"], "output": str(output), "location": relative}


# ---------------------------------------------------------------------------- federation (M8.4)

def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_listed(path):
    pure = PurePosixPath(path)
    return (isinstance(path, str) and path and not pure.is_absolute() and "\\" not in path
            and all(p not in ("", ".", "..") and not p.startswith(".") for p in pure.parts) and path != MANIFEST
            and path not in SIDECARS)


def read_manifest(directory):
    """(snapshot_id, manifest) of a snapshot directory; the manifest must be canonical JSON."""
    path = Path(directory) / MANIFEST
    if not path.is_file() or path.is_symlink():
        raise DawError("snapshot_manifest_missing", str(directory))
    data = path.read_bytes()
    try:
        manifest = json.loads(data)
    except ValueError as e:
        raise DawError("invalid_snapshot_manifest", str(e)) from e
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
        raise DawError("invalid_snapshot_manifest", f"format {FORMAT} with a files list")
    if canonical(manifest) != data:
        raise DawError("invalid_snapshot_manifest", "snapshot.json must be canonical JSON")
    return hashlib.sha256(data).hexdigest(), manifest


def verify_directory(directory, manifest):
    """Every listed file present with its size and sha256; no unlisted files, links or special files."""
    directory = Path(directory)
    listed = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not _safe_listed(entry.get("path")) or entry["path"] in listed \
                or not SNAPSHOT_ID.match(str(entry.get("sha256"))) or not isinstance(entry.get("bytes"), int):
            raise DawError("invalid_snapshot_manifest", f"bad file entry {str(entry)[:200]}")
        listed[entry["path"]] = entry
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            raise DawError("snapshot_link_rejected", relative)
        if path.is_dir():
            continue
        if not path.is_file():
            raise DawError("snapshot_special_file_rejected", relative)
        if relative not in listed and relative != MANIFEST and relative not in SIDECARS:
            raise DawError("snapshot_unlisted_file", relative)
    for relative, entry in sorted(listed.items()):
        path = directory / relative
        if not path.is_file() or path.is_symlink():
            raise DawError("snapshot_file_missing", relative)
        if path.stat().st_size != entry["bytes"] or _hash_file(path) != entry["sha256"]:
            raise DawError("snapshot_hash_mismatch", relative)
    return listed


def import_snapshot(root, source, *, expect=None):
    """Verify a snapshot directory and store it read-only under <commons>/federation/<snapshot_id>/."""
    root = Path(root).expanduser().resolve()
    source = Path(source).expanduser().resolve()
    if not (root / "board.sqlite").is_file():
        raise DawError("community_not_initialized", str(root))
    snapshot, manifest = read_manifest(source)
    if expect and expect != snapshot:
        raise DawError("snapshot_id_mismatch", f"expected {expect}, manifest hashes to {snapshot}")
    verify_directory(source, manifest)
    federation = root / "federation"
    federation.mkdir(exist_ok=True)
    final = federation / snapshot
    if final.exists():
        verify_directory(final, read_manifest(final)[1])
        return snapshot_info(root, snapshot) | {"already_imported": True}
    staging = federation / f".import-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        for entry in [{"path": MANIFEST}] + manifest["files"]:
            target = staging / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / entry["path"], target)
        # Re-verify the copies: the source may change between check and copy.
        if read_manifest(staging)[0] != snapshot:
            raise DawError("snapshot_source_changed", MANIFEST)
        verify_directory(staging, manifest)
        for path in staging.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        staging.rename(final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    receipt = {"snapshot": snapshot, "imported": now(), "files": len(manifest["files"]) + 1,
               "bytes": sum(f["bytes"] for f in manifest["files"]), "scope": manifest.get("scope"),
               "verified": "every listed sha256 and size matched; no unlisted files or links"}
    (federation / f"{snapshot}.import.json").write_bytes(canonical(receipt))
    return snapshot_info(root, snapshot) | {"already_imported": False}


def _snapshot_dir(root, snapshot):
    if not SNAPSHOT_ID.match(snapshot or ""):
        raise DawError("unknown_snapshot", str(snapshot)[:80])
    folder = Path(root) / "federation" / snapshot
    if not (folder / MANIFEST).is_file():
        raise DawError("unknown_snapshot", snapshot)
    return folder


def snapshot_info(root, snapshot, *, verify=False):
    folder = _snapshot_dir(root, snapshot)
    found, manifest = read_manifest(folder)
    receipt_path = Path(root) / "federation" / f"{snapshot}.import.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else None
    info = {"snapshot": snapshot, "scope": manifest.get("scope"), "counts": manifest.get("counts"),
            "files": manifest["files"], "imported": receipt.get("imported") if receipt else None,
            "manifest_matches_id": found == snapshot, "foreign": True, "content_is_untrusted_data": True,
            "note": "Foreign snapshot imported read-only; nothing from it is written into this board."}
    if verify:
        try:
            verify_directory(folder, manifest)
            info["verified"] = found == snapshot
        except DawError as error:
            info.update(verified=False, problem=f"{error.reason}: {error.detail}")
    return info


def list_snapshots(root):
    folder = Path(root) / "federation"
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.iterdir()):
        if path.is_dir() and SNAPSHOT_ID.match(path.name):
            try:
                info = snapshot_info(root, path.name)
            except DawError:
                continue
            out.append({k: v for k, v in info.items() if k != "files"} | {"file_count": len(info["files"])})
    return out


def snapshot_file(root, snapshot, path):
    """(path, media type, filename, attachment) for one listed file of an imported snapshot."""
    folder = _snapshot_dir(root, snapshot)
    _, manifest = read_manifest(folder)
    listed = {entry["path"]: entry for entry in manifest["files"]}
    if path != MANIFEST and path not in listed:
        raise DawError("unknown_snapshot_file", path[:200])
    target = folder / path
    if target.is_symlink() or not target.resolve().is_relative_to(folder.resolve()) or not target.is_file():
        raise DawError("unknown_snapshot_file", path[:200])
    text = Path(path).suffix.lower() in TEXT_SUFFIXES and target.stat().st_size <= 20_000_000
    return target, ("text/plain; charset=utf-8" if text else "application/octet-stream"), Path(path).name, not text
