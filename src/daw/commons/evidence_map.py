"""Evidence map (M4.2): a graph whose every edge is a recorded relation.

Nodes are record identities: posts, artifacts, asset revisions, source snapshots
(receipts), `question:<agent>:<qid>`, participants, marks, claims and frontier
items. Edges come only from rows and events that already exist:

- post -> artifact        post body `evidence.artifacts` (published, immutable)
- post -> question        post body `evidence.notebook` whose snapshot exists in the author's workspace
- post -> post            `post.parent` (reply), `post.supersedes`, request rows (question answered_by answer)
- artifact -> input       `artifact_input` rows; the input is an asset revision or an artifact by
                          `source_identity`, or the bare object when no identity was recorded
- asset -> snapshot       `asset_revision.snapshot_id` (the source receipt)
- question -> artifact    `question_artifact` (produced / considered / reused); reused links are
                          backed or unbacked exactly as `daw.artifacts.reuse_links` reports
- participant -> post     `post.author` (authored) and `evidence_fetched` board events (fetched)
- participant -> question workspace ownership (`agent.trial`)
- participant -> mark -> target   `mark` rows; claim -> post via `claim.post`
- question -> frontier item       `frontier_item.question` and `.author`, only when rows exist

Nothing is inferred: a record named by another record but absent from every store
becomes a node with `present: false` (missing is not the same as unindexed or
selected out). Every edge lists the records it came from so a reader can open them.
The force layout is deterministic and disposable; it is cached under
`<commons>/cache/map/` keyed by the board event sequence, a fingerprint of the
workspace catalogs (which change without board events) and the filters.
"""
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime

from daw.artifacts import reuse_links
from daw.commons.participation import comment_target
from daw.util import DawError, canonical, digest

LAYOUT_VERSION = 2  # bumped when the response shape changes, so cached maps are recomputed
FAMILIES = {"post": "posts", "claim": "posts", "artifact": "artifacts", "asset": "sources", "snapshot": "sources",
            "object": "sources", "question": "questions", "frontier_item": "questions", "participant": "participants",
            "mark": "participants"}
DERIVATION = {"input", "source_receipt"}
TIMELESS = {"participant", "object"}  # Hubs kept by the time filter while a dated record still links them.
RELATIONS = {
    "evidence": ("solid", "post body lists the artifact as evidence"),
    "notebook": ("solid", "post body carries a notebook snapshot of the question"),
    "reply_to": ("solid", "post.parent"),
    "supersedes": ("solid", "post.supersedes (a correction by the same author)"),
    "answered_by": ("solid", "request row: question post answered by a post"),
    "input": ("solid", "artifact_input row (registered derivation input)"),
    "source_receipt": ("solid", "asset_revision.snapshot_id (retrieval receipt)"),
    "produced": ("solid", "question_artifact: registered in this question"),
    "considered": ("dashed", "question_artifact: retrieved, not asserted as used"),
    "reused": ("solid", "question_artifact: reused; dashed when unbacked (no reason, never a registration input)"),
    "authored": ("solid", "post.author"),
    "fetched": ("dashed", "evidence_fetched board event"),
    "owns": ("solid", "agent.trial: the participant's research workspace"),
    "fork_of": ("dashed", "agent.parent"),
    "marked": ("solid", "mark row (attribution, never a status change)"),
    "mark_on": ("solid", "mark row target"),
    "claim_of": ("solid", "claim row: claim extracted from a post"),
    "comments_on": ("solid", "comment post evidence target"),
    "frontier": ("solid", "frontier_item row for this question"),
}
DEFAULT_LIMIT = 2000
MAX_LIMIT = 10000


class Graph:
    def __init__(self):
        self.nodes, self.edges = {}, {}

    def node(self, identity, kind, *, store=None, present=True, **attrs):
        node = self.nodes.get(identity)
        if node is None:
            node = self.nodes[identity] = {"id": identity, "kind": kind, "family": FAMILIES[kind], "label": identity,
                                           "present": present, "stores": []}
        elif present and not node["present"]:
            node["present"] = True
        for key, value in attrs.items():
            if value is not None and (node.get(key) is None or key == "label" and node["label"] == identity):
                node[key] = value
        if store and store not in node["stores"]:
            node["stores"].append(store)
        return node

    def placeholder(self, identity, kind):
        """A record named by another record but not (yet) found in any store."""
        return self.nodes.get(identity) or self.node(identity, kind, present=False)

    def edge(self, source, target, relation, record, *, style=None, created=None, **attrs):
        key = (source, target, relation)
        edge = self.edges.get(key)
        if edge is None:
            edge = self.edges[key] = {"id": "edge_" + digest(list(key))[:24], "source": source, "target": target,
                                      "relation": relation, "style": style or RELATIONS[relation][0],
                                      "created": created, "records": []}
        if record not in edge["records"]:
            edge["records"].append(record)
        for name, value in attrs.items():
            edge.setdefault(name, value)
        if style == "solid":
            edge["style"] = "solid"  # Any backed record for the same relation backs the drawn edge.
        return edge


def _title(ws, manifest_blob):
    try:
        manifest = ws.json_blob(manifest_blob)
    except (DawError, OSError, ValueError):
        return None, None
    output = manifest.get("output") if isinstance(manifest.get("output"), dict) else {}
    return manifest.get("title"), output.get("name")


def _basename(locator):
    text = str(locator or "").rstrip("/")
    return text.rsplit("/", 1)[-1] or text


def _add_catalog(graph, ws, store, *, agent=None):
    """Artifacts, derivation inputs, input assets and their receipts from one catalog (library or workspace)."""
    for row in ws.rows("SELECT id,output_role,manifest_blob,output_blob,created FROM artifact ORDER BY id"):
        existing = graph.nodes.get(row["id"])
        title, name = (existing.get("title"), existing.get("output_name")) if existing and existing.get("title") \
            else _title(ws, row["manifest_blob"])
        graph.node(row["id"], "artifact", store=store, label=title or row["id"], title=title, output_name=name,
                   output_role=row["output_role"], output_blob=row["output_blob"], created=row["created"])
    assets = set()
    for row in ws.rows("SELECT i.*,a.created FROM artifact_input i JOIN artifact a ON a.id=i.artifact_id "
                       "ORDER BY i.artifact_id,i.blob,i.role,i.source_identity"):
        identity = row["source_identity"]
        if identity.startswith("asset_"):
            graph.placeholder(identity, "asset")
            assets.add(identity)
        elif identity.startswith("artifact_"):
            graph.placeholder(identity, "artifact")
        else:
            identity = row["blob"]
            graph.node(identity, "object", store=store, label="object " + identity[:12], sha256=identity)
        graph.edge(row["artifact_id"], identity, "input",
                   {"store": store, "table": "artifact_input", "artifact_id": row["artifact_id"], "blob": row["blob"],
                    "role": row["role"], "source_identity": row["source_identity"]},
                   created=row["created"], role=row["role"])
    for identity in sorted(assets):
        asset = ws.one("SELECT id,resource_id,snapshot_id,blob,access,body,created FROM asset_revision WHERE id=?",
                       (identity,))
        if not asset:
            continue
        try:
            body = json.loads(asset["body"])
        except ValueError:
            body = {}
        graph.node(identity, "asset", store=store, label=body.get("name") or identity, access=asset["access"],
                   blob=asset["blob"], created=asset["created"])
        if asset["snapshot_id"]:
            snap = ws.one("SELECT id,locator,retrieved,outcome,blob FROM snapshot WHERE id=?", (asset["snapshot_id"],))
            if snap:
                graph.node(snap["id"], "snapshot", store=store, label=f"{snap['outcome']} · {_basename(snap['locator'])}",
                           outcome=snap["outcome"], blob=snap["blob"], created=snap["retrieved"])
            else:
                graph.placeholder(asset["snapshot_id"], "snapshot")
            graph.edge(identity, asset["snapshot_id"], "source_receipt",
                       {"store": store, "table": "asset_revision", "id": identity, "field": "snapshot_id"},
                       created=asset["created"])
    if agent is None:
        return
    questions = ws.rows("SELECT id,title,status,created,updated,current_work FROM question ORDER BY id")
    for q in questions:
        node = question_node(agent["id"], q["id"])
        graph.node(node, "question", store=store, label=q["title"], title=q["title"], agent=agent["id"],
                   agent_name=agent["name"], qid=q["id"], status=q["status"], created=q["created"], updated=q["updated"])
        graph.edge(agent["id"], node, "owns", {"store": "board", "table": "agent", "id": agent["id"], "field": "trial"},
                   created=q["created"])
    created = {r["id"]: r["created"] for r in ws.rows(
        "SELECT e.id,e.created FROM work_event e JOIN question_artifact qa ON qa.event_id=e.id")}
    events = {(r["question_id"], r["artifact_id"], r["relationship"]): r["event_id"]
              for r in ws.rows("SELECT * FROM question_artifact")}
    for link in reuse_links(ws):
        event = events[(link["question"], link["artifact"], link["relationship"])]
        backed = link.get("backed")
        style = "dashed" if link["relationship"] == "considered" or backed is False else "solid"
        graph.placeholder(link["artifact"], "artifact")
        extra = {"backed": backed, "reason": link.get("reason"), "input_to": link.get("input_to")} \
            if link["relationship"] == "reused" else {}
        graph.edge(question_node(agent["id"], link["question"]), link["artifact"], link["relationship"],
                   {"store": store, "table": "question_artifact", "question_id": link["question"],
                    "artifact_id": link["artifact"], "relationship": link["relationship"], "event": event},
                   style=style, created=created.get(event), **extra)


def question_node(agent, qid):
    return f"question:{agent}:{qid}"


def _evidence(content):
    evidence = content.get("evidence") if isinstance(content, dict) else None
    return evidence if isinstance(evidence, dict) else {}


def build(view):
    """The full recorded graph of one commons (unfiltered)."""
    graph = Graph()
    agents = view.rows("SELECT id,name,kind,parent,trial,created FROM agent ORDER BY created,id")
    for agent in agents:
        graph.node(agent["id"], "participant", store="board", label=agent["name"], name=agent["name"],
                   participant_kind=agent["kind"], created=agent["created"])
    for agent in agents:
        if agent["parent"]:
            graph.edge(agent["id"], agent["parent"], "fork_of",
                       {"store": "board", "table": "agent", "id": agent["id"], "field": "parent"}, created=agent["created"])
    _add_catalog(graph, view.library, "library")
    workspaces = {}
    for agent in agents:
        if not agent["trial"]:
            continue
        try:
            ws = view.workspace(agent["id"])
        except DawError:
            continue  # A participant whose checkout is missing contributes no workspace records.
        workspaces[agent["id"]] = ws
        _add_catalog(graph, ws, "workspace:" + agent["id"], agent=agent)
    hidden = {r["target_id"] for r in view.rows(
        "SELECT target_id FROM moderation WHERE target_kind='post' AND state='hidden'")}
    for post in view.rows("SELECT id,author,channel,parent,supersedes,body_blob,created FROM post ORDER BY seq"):
        try:
            content = view.library.json_blob(post["body_blob"])
        except (DawError, OSError, ValueError):
            content = {}
        record = {"store": "board", "table": "post", "id": post["id"]}
        evidence = _evidence(content)
        graph.node(post["id"], "post", store="board", label=content.get("title") or post["id"],
                   title=content.get("title"), post_kind=content.get("kind"), author=post["author"],
                   channel=post["channel"], created=post["created"], hidden=post["id"] in hidden,
                   run=evidence.get("run"))
        graph.edge(post["author"], post["id"], "authored", {**record, "field": "author"}, created=post["created"])
        if post["parent"]:
            graph.edge(post["id"], post["parent"], "reply_to", {**record, "field": "parent"}, created=post["created"])
        if post["supersedes"]:
            graph.edge(post["id"], post["supersedes"], "supersedes", {**record, "field": "supersedes"},
                       created=post["created"])
        for artifact in evidence.get("artifacts") or []:
            if isinstance(artifact, str):
                graph.placeholder(artifact, "artifact")
                graph.edge(post["id"], artifact, "evidence",
                           {**record, "field": "evidence.artifacts", "blob": post["body_blob"]}, created=post["created"])
        notebook = evidence.get("notebook")
        ws = workspaces.get(post["author"])
        if isinstance(notebook, dict) and ws and isinstance(notebook.get("snapshot"), str) and ws.one(
                "SELECT id FROM work_snapshot WHERE id=? AND question_id=?", (notebook["snapshot"], notebook.get("question"))):
            graph.edge(post["id"], question_node(post["author"], notebook["question"]), "notebook",
                       {**record, "field": "evidence.notebook", "blob": post["body_blob"],
                        "snapshot": notebook["snapshot"]}, created=post["created"])
        target = _comment_target(content, evidence)
        if target:
            graph.placeholder(*target)
            graph.edge(post["id"], target[0], "comments_on", {**record, "field": "evidence.target"},
                       created=post["created"])
    for request in view.rows("SELECT id,post,answer,updated FROM request WHERE answer IS NOT NULL ORDER BY created,id"):
        graph.edge(request["post"], request["answer"], "answered_by",
                   {"store": "board", "table": "request", "id": request["id"]}, created=request["updated"])
    for event in view.rows("SELECT seq,body,created FROM event WHERE kind='evidence_fetched' ORDER BY seq"):
        body = json.loads(event["body"])
        if isinstance(body.get("reader"), str) and isinstance(body.get("post"), str):
            graph.placeholder(body["reader"], "participant")
            graph.edge(body["reader"], body["post"], "fetched",
                       {"store": "board", "table": "event", "seq": event["seq"], "question": body.get("question")},
                       created=event["created"])
    for claim in view.rows("SELECT id,post,author,ordinal,status,created FROM claim ORDER BY created,id"):
        graph.node(claim["id"], "claim", store="board", label=f"claim {claim['ordinal']} · {claim['status']}",
                   status=claim["status"], author=claim["author"], created=claim["created"])
        graph.edge(claim["id"], claim["post"], "claim_of", {"store": "board", "table": "claim", "id": claim["id"]},
                   created=claim["created"])
    for mark in view.rows("SELECT id,participant,target_kind,target_id,kind,created FROM mark ORDER BY created,id"):
        record = {"store": "board", "table": "mark", "id": mark["id"]}
        graph.node(mark["id"], "mark", store="board", label=mark["kind"].replace("_", " "), mark_kind=mark["kind"],
                   created=mark["created"])
        graph.edge(mark["participant"], mark["id"], "marked", record, created=mark["created"])
        kind = {"post": "post", "artifact": "artifact", "claim": "claim"}.get(mark["target_kind"])
        if kind:
            graph.placeholder(mark["target_id"], kind)
            graph.edge(mark["id"], mark["target_id"], "mark_on", record, created=mark["created"])
    for item in view.rows("SELECT id,question,author,kind,status,text,promoted_to,created FROM frontier_item "
                          "ORDER BY created,id"):
        graph.node(item["id"], "frontier_item", store="board", label=item["text"][:80], frontier_kind=item["kind"],
                   status=item["status"], promoted_to=item["promoted_to"], created=item["created"])
        question = question_node(item["author"], item["question"])
        graph.placeholder(question, "question")
        graph.edge(question, item["id"], "frontier", {"store": "board", "table": "frontier_item", "id": item["id"]},
                   created=item["created"])
    for node in graph.nodes.values():
        node["stores"].sort()
    _label_superseded(graph)
    return graph


def _label_superseded(graph):
    """Flow B: re-label a superseded post and every edge into it from the recorded `post.supersedes` edges.

    Nothing new is drawn: the post node carries `superseded_by` (its recorded superseders) and each other
    edge whose target is that post carries `into_superseded` naming them, so readers, claims, replies and
    marks of the old post are shown as pointing at a corrected record."""
    superseded = {}
    for edge in graph.edges.values():
        if edge["relation"] == "supersedes":
            superseded.setdefault(edge["target"], []).append(edge["source"])
    for post, newer in superseded.items():
        node = graph.nodes.get(post)
        if node is not None:
            node["superseded_by"] = sorted(newer)
            node["label"] = f"{node['label']} (superseded)"
    for edge in graph.edges.values():
        if edge["target"] in superseded and edge["relation"] != "supersedes":
            edge["into_superseded"] = sorted(superseded[edge["target"]])


def _comment_target(content, evidence):
    """A comment post records its target in evidence; only post and artifact targets map to nodes directly."""
    if content.get("kind") != "comment":
        return None
    kind, identity = comment_target(evidence)
    if not isinstance(identity, str):
        return None
    if kind in ("post", "artifact"):
        return identity, kind
    if kind == "question":
        if identity.startswith("question:"):
            return identity, "question"
        if identity.count(":") == 1:
            return "question:" + identity, "question"
    return None


def fingerprint(view):
    """Workspace catalogs change without board events (registrations, links); include their extent in cache keys."""
    parts = [view.sequence()]
    for table, column in (("mark", "created"), ("frontier_item", "updated"), ("claim", "created")):
        parts.append(view.one(f"SELECT count(*) AS n, max({column}) AS m FROM {table}"))
    stores = [("library", view.library)]
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY id"):
        try:
            stores.append((agent["id"], view.workspace(agent["id"])))
        except DawError:
            stores.append((agent["id"], None))
    for name, ws in stores:
        if ws is None:
            parts.append([name, None])
            continue
        parts.append([name] + [ws.one(sql) for sql in (
            "SELECT count(*) AS n, max(created) AS m FROM artifact",
            "SELECT count(*) AS n FROM artifact_input",
            "SELECT count(*) AS n, max(created) AS m FROM work_event",
            "SELECT count(*) AS n, max(updated) AS m FROM question",
            "SELECT count(*) AS n FROM asset_revision")])
    return digest(parts)[:32]


def _neighbourhood(graph, seeds):
    """Two hops from the seeds without expanding through participant hubs, plus the upstream derivation closure."""
    adjacent = {}
    for edge in graph.edges.values():
        adjacent.setdefault(edge["source"], set()).add(edge["target"])
        adjacent.setdefault(edge["target"], set()).add(edge["source"])
    keep, layer = set(seeds), set(seeds)
    for _ in range(2):
        following = set()
        for identity in layer:
            if identity not in seeds and graph.nodes[identity]["kind"] == "participant":
                continue
            following |= adjacent.get(identity, set()) - keep
        keep |= following
        layer = following
    upstream = {}
    for edge in graph.edges.values():
        if edge["relation"] in DERIVATION:
            upstream.setdefault(edge["source"], set()).add(edge["target"])
    stack = [n for n in keep if n in upstream]
    while stack:
        for parent in upstream.get(stack.pop(), ()):
            if parent not in keep:
                keep.add(parent)
                stack.append(parent)
    return keep


def resolve_question(view, value):
    """`question:<agent>:<qid>`, `<agent id or name>:<qid>` or a bare qid (every workspace holding it)."""
    text = value.removeprefix("question:")
    if ":" in text:
        agent, qid = text.split(":", 1)
        return [question_node(view.participant(agent)["id"], qid)]
    return [text]


def select(graph, *, questions=(), participant=None, since=None, until=None, families=None, limit=DEFAULT_LIMIT):
    """Apply filters to a built graph. Returns (nodes, edges, seeds, total) with deterministic ordering."""
    keep = set(graph.nodes)
    seeds = set()
    if questions:
        wanted = set()
        for value in questions:
            if value.startswith("question:"):
                wanted.add(value)
            else:
                wanted |= {n for n, node in graph.nodes.items() if node["kind"] == "question" and node.get("qid") == value}
        found = wanted & set(graph.nodes)
        if not found:
            raise DawError("unknown_question", ", ".join(sorted(questions)))
        seeds |= found
        keep &= _neighbourhood(graph, found)
    if participant:
        if participant not in graph.nodes:
            raise DawError("unknown_participant", participant)
        seeds.add(participant)
        keep &= _neighbourhood(graph, {participant})
    def within(stamp):
        return not stamp or ((not since or stamp >= since) and (not until or stamp <= until))

    def dated(node):
        return node["kind"] not in TIMELESS and node.get("created")
    if since or until:
        keep = {n for n in keep if n in seeds or not dated(graph.nodes[n]) or within(graph.nodes[n]["created"])}
    if families:
        unknown = set(families) - set(FAMILIES.values())
        if unknown:
            raise DawError("invalid_map_family", ", ".join(sorted(unknown)))
        keep = {n for n in keep if graph.nodes[n]["family"] in families}
    edges = [e for e in graph.edges.values() if e["source"] in keep and e["target"] in keep]
    if since or until:
        edges = [e for e in edges if within(e.get("created"))]
        # Timeless hubs (participants, bare objects) stay only while a dated record still links them.
        linked = {e["source"] for e in edges} | {e["target"] for e in edges}
        keep = {n for n in keep if n in seeds or dated(graph.nodes[n]) or n in linked}
    total = len(keep)
    if len(keep) > limit:
        degree = {}
        for edge in edges:
            degree[edge["source"]] = degree.get(edge["source"], 0) + 1
            degree[edge["target"]] = degree.get(edge["target"], 0) + 1
        ranked = sorted(keep, key=lambda n: (n not in seeds, -degree.get(n, 0), n))
        keep = set(ranked[:limit])
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
    nodes = [graph.nodes[n] for n in sorted(keep)]
    edges.sort(key=lambda e: (e["source"], e["target"], e["relation"]))
    return nodes, edges, sorted(seeds), total


def layout(node_ids, edges, *, seed=7, iterations=None, spacing=40.0):
    """Deterministic Fruchterman-Reingold layout in pure Python.

    Seeded initial positions from a hash of each identity; repulsion only within a
    grid neighbourhood (linear time per iteration); bounded iterations with linear
    cooling. Returns {identity: [x, y]} rounded to 0.1.
    """
    ids = sorted(node_ids)
    n = len(ids)
    if not n:
        return {}
    index = {identity: i for i, identity in enumerate(ids)}
    radius = spacing * math.sqrt(n)
    xs, ys = [0.0] * n, [0.0] * n
    for i, identity in enumerate(ids):
        h = hashlib.sha256(f"{seed}:{identity}".encode()).digest()
        angle = int.from_bytes(h[:4], "big") / 2**32 * 2 * math.pi
        r = radius * math.sqrt(int.from_bytes(h[4:8], "big") / 2**32)
        xs[i], ys[i] = r * math.cos(angle), r * math.sin(angle)
    pairs = sorted({(index[e["source"]], index[e["target"]]) for e in edges
                    if e["source"] in index and e["target"] in index and e["source"] != e["target"]})
    steps = iterations if iterations is not None else max(30, min(250, 40000 // n))
    k, cell = spacing, 2 * spacing
    temperature = radius / 4 + spacing
    for step in range(steps):
        dx, dy = [0.0] * n, [0.0] * n
        grid = {}
        for i in range(n):
            grid.setdefault((math.floor(xs[i] / cell), math.floor(ys[i] / cell)), []).append(i)
        for (gx, gy), members in grid.items():
            nearby = [j for ox in (-1, 0, 1) for oy in (-1, 0, 1) for j in grid.get((gx + ox, gy + oy), ())]
            for i in members:
                for j in nearby:
                    if j <= i:
                        continue
                    ddx, ddy = xs[i] - xs[j], ys[i] - ys[j]
                    dist2 = ddx * ddx + ddy * ddy
                    if dist2 > cell * cell:
                        continue
                    if dist2 < 1e-6:
                        ddx, ddy, dist2 = (i - j) * 0.01 + 0.01, 0.01, 1e-4 + ((i - j) * 0.01) ** 2
                    force = k * k / dist2
                    dx[i] += ddx * force
                    dy[i] += ddy * force
                    dx[j] -= ddx * force
                    dy[j] -= ddy * force
        for i, j in pairs:
            ddx, ddy = xs[i] - xs[j], ys[i] - ys[j]
            dist = math.sqrt(ddx * ddx + ddy * ddy) or 1e-3
            force = dist / k
            dx[i] -= ddx * force
            dy[i] -= ddy * force
            dx[j] += ddx * force
            dy[j] += ddy * force
        for i in range(n):
            dx[i] -= xs[i] * 0.02
            dy[i] -= ys[i] * 0.02
            length = math.sqrt(dx[i] * dx[i] + dy[i] * dy[i])
            if length > 0:
                scale = min(length, temperature) / length
                xs[i] += dx[i] * scale
                ys[i] += dy[i] * scale
        temperature = max(1.0, temperature * (1 - (step + 1) / (steps + 1)))
    return {identity: [round(xs[i], 1), round(ys[i], 1)] for i, identity in enumerate(ids)}


def _cache_dir(view):
    return view.root / "cache" / "map"


def _read_cache(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_cache(directory, path, value, *, keep=256):
    """Atomic, best effort: the cache is disposable and never authoritative."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value))
        os.replace(temp, path)
        entries = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in entries[:-keep]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def _instant(value, name):
    """ISO 8601 → UTC isoformat, comparable with recorded `created` stamps; naive times are UTC."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as e:
        raise DawError("invalid_map_time", f"{name} must be ISO 8601") from e
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def evidence_map(view, *, question=None, participant=None, since=None, until=None, family=None,
                 limit=DEFAULT_LIMIT, use_cache=True):
    """GET /api/map: recorded graph, filters and a cached deterministic layout."""
    if not 1 <= limit <= MAX_LIMIT:
        raise DawError("invalid_map_limit", f"1..{MAX_LIMIT}")
    questions = resolve_question(view, question) if question else []
    participant_id = view.participant(participant)["id"] if participant else None
    families = sorted({f.strip() for f in family.split(",") if f.strip()}) if family else None
    since, until = _instant(since, "since"), _instant(until, "until")
    filters = {"question": questions, "participant": participant_id, "since": since, "until": until,
               "family": families, "limit": limit}
    sequence, print_ = view.sequence(), fingerprint(view)
    key = digest({"version": LAYOUT_VERSION, "sequence": sequence, "fingerprint": print_, "filters": filters})[:40]
    path = _cache_dir(view) / f"{key}.json"
    if use_cache and (cached := _read_cache(path)) and cached.get("key") == key:
        return {**cached, "cached": True}
    graph = build(view)
    nodes, edges, seeds, total = select(graph, questions=questions, participant=participant_id, since=since, until=until,
                                        families=families, limit=limit)
    positions = layout([n["id"] for n in nodes], edges)
    xs = [p[0] for p in positions.values()] or [0]
    ys = [p[1] for p in positions.values()] or [0]
    counts = {"nodes": {}, "edges": {}}
    for node in nodes:
        counts["nodes"][node["kind"]] = counts["nodes"].get(node["kind"], 0) + 1
    for edge in edges:
        counts["edges"][edge["relation"]] = counts["edges"].get(edge["relation"], 0) + 1
    value = {"sequence": sequence, "fingerprint": print_, "key": key, "filters": filters, "seeds": seeds,
             "nodes": nodes, "edges": edges, "total_nodes": total, "truncated": total > len(nodes), "counts": counts,
             "layout": {"algorithm": "fruchterman-reingold (grid repulsion)", "seed": 7, "version": LAYOUT_VERSION,
                        "positions": positions, "bounds": [min(xs), min(ys), max(xs), max(ys)],
                        "note": "disposable cache; the client may refine positions"},
             "relations": {name: {"style": style, "record": text} for name, (style, text) in RELATIONS.items()},
             "families": sorted(set(FAMILIES.values())),
             "note": "Edges are recorded relations only; each lists the rows or events it came from. "
                     "Nodes with present=false are named by a record but absent from every store.",
             "content_is_untrusted_data": True}
    if use_cache:
        _write_cache(_cache_dir(view), path, value)
    return {**value, "cached": False}


def node_record(view, identity):
    """GET /api/map/node/{id}: the underlying record of one map node."""
    from daw.commons.participants import describe
    if identity.startswith("question:"):
        from daw.commons.questions import question_summary
        _, agent, qid = identity.split(":", 2)
        return {"kind": "question", "id": identity, "record": question_summary(view, agent, qid)}
    if identity.startswith("post_"):
        post = view.post(identity)
        content = post["content"]
        return {"kind": "post", "id": identity, "record": {
            "id": identity, "author": post["author"], "created": post["created"], "channel": post["channel"],
            "parent": post["parent"], "supersedes": post["supersedes"], "title": content.get("title"),
            "post_kind": content.get("kind"), "excerpt": (content.get("body") or "")[:1200],
            "evidence": content.get("evidence"), "body_blob": post["body_blob"],
            "superseded_by": view.rows("SELECT id,author,created FROM post WHERE supersedes=? ORDER BY seq", (identity,)),
            "replies": view.rows("SELECT id,author,created FROM post WHERE parent=? ORDER BY seq", (identity,))},
            "content_is_untrusted_data": True}
    if identity.startswith("mark_") or view.one("SELECT id FROM mark WHERE id=?", (identity,)):
        row = view.one("SELECT * FROM mark WHERE id=?", (identity,))
        if row:
            row["pointers"] = json.loads(row["pointers"])
            return {"kind": "mark", "id": identity, "record": row, "content_is_untrusted_data": True}
    if view.one("SELECT id FROM agent WHERE id=?", (identity,)):
        return {"kind": "participant", "id": identity, "record": describe(view.participant(identity))}
    for table, kind in (("claim", "claim"), ("frontier_item", "frontier_item")):
        row = view.one(f"SELECT * FROM {table} WHERE id=?", (identity,))
        if row:
            for field in ("scope", "pointers"):
                if isinstance(row.get(field), str):
                    try:
                        row[field] = json.loads(row[field])
                    except ValueError:
                        pass
            return {"kind": kind, "id": identity, "record": row, "content_is_untrusted_data": True}
    stores = [("library", view.library)]
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
        try:
            stores.append(("workspace:" + agent["id"], view.workspace(agent["id"])))
        except DawError:
            continue
    found = []
    for name, ws in stores:
        if identity.startswith("artifact_"):
            row = ws.one("SELECT * FROM artifact WHERE id=?", (identity,))
            if row:
                found.append({"store": name, "artifact": row, "manifest": ws.json_blob(row["manifest_blob"], verify=True),
                              "inputs": ws.rows("SELECT * FROM artifact_input WHERE artifact_id=? ORDER BY blob,role",
                                                (identity,)),
                              "questions": ws.rows("SELECT question_id,relationship,event_id FROM question_artifact "
                                                   "WHERE artifact_id=? ORDER BY question_id,relationship", (identity,))})
        elif identity.startswith("asset_"):
            row = ws.one("SELECT * FROM asset_revision WHERE id=?", (identity,))
            if row:
                row["body"] = json.loads(row["body"])
                receipt = ws.one("SELECT * FROM snapshot WHERE id=?", (row["snapshot_id"],)) if row["snapshot_id"] else None
                found.append({"store": name, "asset": row, "source_receipt": _snapshot(receipt)})
        elif identity.startswith("snap_"):
            row = ws.one("SELECT * FROM snapshot WHERE id=?", (identity,))
            if row:
                found.append({"store": name, "snapshot": _snapshot(row)})
        elif len(identity) == 64 and all(c in "0123456789abcdef" for c in identity):
            row = ws.one("SELECT sha256,size,classification,integrity FROM blob WHERE sha256=?", (identity,))
            if row:
                found.append({"store": name, "object": row})
    if not found:
        raise DawError("unknown_map_node", identity)
    kind = ("artifact" if identity.startswith("artifact_") else "asset" if identity.startswith("asset_")
            else "snapshot" if identity.startswith("snap_") else "object")
    return {"kind": kind, "id": identity, "records": found, "content_is_untrusted_data": True}


def _snapshot(row):
    if not row:
        return None
    try:
        row = {**row, "body": json.loads(row["body"])}
    except ValueError:
        pass
    return row


def question_subgraph(ws, store, agent, qid):
    """The question's artifacts with their recorded derivation closure inside one workspace (for question pages)."""
    graph = Graph()
    _add_catalog(graph, ws, store, agent=agent)
    seed = question_node(agent["id"], qid)
    if seed not in graph.nodes:
        raise DawError("unknown_question", qid)
    linked = {e["target"] for e in graph.edges.values() if e["source"] == seed}
    keep = {seed} | linked
    upstream = {}
    for edge in graph.edges.values():
        if edge["relation"] in DERIVATION:
            upstream.setdefault(edge["source"], set()).add(edge["target"])
    stack = list(linked)
    while stack:
        for parent in upstream.get(stack.pop(), ()):
            if parent not in keep:
                keep.add(parent)
                stack.append(parent)
    nodes = [graph.nodes[n] for n in sorted(keep)]
    edges = sorted((e for e in graph.edges.values() if e["source"] in keep and e["target"] in keep),
                   key=lambda e: (e["source"], e["target"], e["relation"]))
    return {"nodes": nodes, "edges": edges, "positions": layout(keep, edges, iterations=120)}
