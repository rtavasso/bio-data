import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Untrusted } from "../Untrusted";
import { MarkForm, PromoteForm } from "../participation/Actions";
import { WatcherPanel } from "../discovery/WatcherPanel";
import type { Claim, FrontierItem, Pointer } from "../../types/ledger";

// Shared pieces of the claim ledger and frontier screens. Every author-stated string renders inside
// <Untrusted>; pointers link to the records they name and say when a named record is absent.

export function PointerLink({ pointer }: { pointer: Pointer }) {
  const isPost = pointer.kind === "post" || (pointer.kind === "locator" && pointer.id.startsWith("post_"));
  const missing = pointer.present === false
    ? <span className="ledger-badge bad"> {isPost ? "not on this board" : "missing"}</span> : null;
  const short = pointer.id.length > 24 ? `${pointer.id.slice(0, 20)}…` : pointer.id;
  let target: ReactNode = <span className="mono">{short}</span>;
  if (isPost && pointer.present !== false) {
    target = <Link className="mono" to={`/post/${pointer.id}`}>{short}</Link>;
  } else if (pointer.kind === "artifact" || (pointer.kind === "locator" && pointer.id.startsWith("artifact_"))) {
    target = <Link className="mono" to={`/artifact/${pointer.id}`}>{short}</Link>;
  }
  return (
    <span className="ledger-pointer" title={pointer.id}>
      <span className="ledger-pointer-kind">{pointer.kind}</span> {target}
      {pointer.locator && <span className="muted"> @ {pointer.locator}</span>}
      {missing}
    </span>
  );
}

export function Pointers({ pointers }: { pointers: Pointer[] }) {
  if (!pointers.length) return <span className="muted">no pointers</span>;
  return (
    <ul className="ledger-pointers" aria-label="Pointers">
      {pointers.map((p, n) => <li key={`${p.kind}:${p.id}:${n}`}><PointerLink pointer={p} /></li>)}
    </ul>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`ledger-badge status-${status}`}>{status.replace("_", " ")}</span>;
}

export function Toggle({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="ledger-toggle">
      <button type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>{label}</button>
      {open && <div className="ledger-toggle-body">{children}</div>}
    </span>
  );
}

export function ClaimCard({ claim, onChange }: { claim: Claim; onChange?: () => void }) {
  if (claim.hidden && claim.scope === undefined) {
    return (
      <article className="ledger-card withdrawn" aria-label={`Claim ${claim.id}`}>
        <p className="muted">
          Claim of a <Link to={`/post/${claim.post}`}>post hidden by moderation</Link>: {claim.reason ?? "no reason recorded"}.
        </p>
        <span className="mono muted">{claim.id}</span>
      </article>
    );
  }
  const scope = Object.entries(claim.scope).filter(([, v]) => v);
  return (
    <article className={`ledger-card${claim.status === "withdrawn" ? " withdrawn" : ""}`} aria-label={`Claim ${claim.id}`}>
      <header className="ledger-card-head">
        <StatusBadge status={claim.status} />
        {claim.stated_status && claim.stated_status !== claim.status && (
          <span className="muted">stated: {claim.stated_status}</span>
        )}
        <span className="muted">
          by <Link to={`/agent/${claim.author}`}>{claim.author_name ?? claim.author}</Link> in{" "}
          <Link to={`/post/${claim.post}`}>{claim.post_title ?? claim.post}</Link>
        </span>
      </header>
      {claim.withdrawn_by && (
        <p className="ledger-withdrawn" role="note">
          Withdrawn: superseded by <Link to={`/post/${claim.withdrawn_by}`}>{claim.withdrawn_by}</Link>. The original claim bytes are unchanged.
        </p>
      )}
      <Untrusted author={claim.author_name ?? claim.author}>
        <p className="ledger-text">{claim.text}</p>
        {scope.length > 0 && (
          <dl className="ledger-scope">
            {scope.map(([k, v]) => (
              <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
        )}
      </Untrusted>
      <Pointers pointers={claim.pointers} />
      {claim.marks.length > 0 && (
        <ul className="ledger-marks" aria-label="Marks">
          {claim.marks.map((m) => (
            <li key={m.id}>
              <span className="ledger-badge">{m.kind.replace("_", " ")}</span>{" "}
              <Link to={`/agent/${m.participant}`}>{m.participant}</Link>: <Untrusted>{m.note}</Untrusted>
            </li>
          ))}
        </ul>
      )}
      <footer className="ledger-actions">
        <Link className="mono muted" to={`/claims/${claim.id}`}>{claim.id}</Link>
        <Toggle label="Mark"><MarkForm targetKind="claim" targetId={claim.id} onDone={onChange} /></Toggle>
      </footer>
    </article>
  );
}

// The agent-recorded query (text or {text}/{query}) prefills the form; the person attaches it as a watcher.
function queryText(query: FrontierItem["watcher_query"]): string | undefined {
  if (!query) return undefined;
  if (typeof query === "string") return query;
  for (const key of ["text", "query"] as const) if (typeof query[key] === "string") return query[key] as string;
  return JSON.stringify(query);
}

export function WatchSummary({ item }: { item: FrontierItem }) {
  const { watch } = item;
  if (!watch.watchers.length && !watch.runs) {
    return <span className="muted">{item.watcher_query ? "watcher query recorded, not attached" : "no watcher"}</span>;
  }
  return (
    <span>
      {watch.watchers.length} watcher{watch.watchers.length === 1 ? "" : "s"} · {watch.runs} run{watch.runs === 1 ? "" : "s"} · {watch.found} found
      {watch.last_run && <span className="muted"> · last {watch.last_run.created.slice(0, 10)}</span>}
    </span>
  );
}

// candidate_evidence is set either by a watcher run (a notice to the author) or by the author's own status event.
const SET_BY: Record<string, string> = {
  watcher: "set by watcher", author: "set by author", "author and watcher": "set by author and watcher",
  unrecorded: "setter not recorded", scouting: "set by scouting",
};

function CandidateSource({ item }: { item: FrontierItem }) {
  const evidence = item.candidate_evidence;
  if (!evidence) return null;
  const run = evidence.records.find((r) => r.by === "watcher" && r.post);
  const label = <span className={`ledger-badge set-by set-by-${evidence.set_by.replaceAll(" ", "-")}`}>{SET_BY[evidence.set_by] ?? evidence.set_by}</span>;
  return run?.post ? <Link to={`/post/${run.post}`} title="The watcher's notice">{label}</Link> : label;
}

// V5 scouting deliverables: every dataset a scouting task inspected for the item, eligible or rejected, with the
// scout's reason and its inspection receipt. Reasons are untrusted, attributed text.
export function Datasets({ item, open = false }: { item: FrontierItem; open?: boolean }) {
  const datasets = item.datasets ?? [];
  const summary = item.datasets_summary;
  if (!datasets.length || !summary) return null;
  return (
    <details className="ledger-datasets" open={open}>
      <summary>
        Datasets inspected: {summary.inspected} ({summary.eligible} eligible, {summary.rejected} rejected
        {summary.withheld ? `, ${summary.withheld} withheld` : ""})
      </summary>
      <ul aria-label="Inspected datasets">
        {datasets.map((d, n) => d.hidden ? (
          <li key={`hidden-${n}`} className="muted">A dataset listed in a <Link to={`/post/${d.post}`}>post hidden by moderation</Link>.</li>
        ) : (
          <li key={`${d.accession}-${d.event ?? d.post}-${n}`}>
            <span className={`ledger-badge ${d.eligible ? "status-supported" : "bad"}`}>{d.eligible ? "eligible" : "rejected"}</span>{" "}
            <span className="mono">{d.accession}</span>:{" "}
            <Untrusted author={d.recorded_by}>{d.reason}</Untrusted>
            {d.receipt && <> <PointerLink pointer={d.receipt} /></>}
            {d.post && <span className="muted"> · from <Link to={`/post/${d.post}`}>the scouting answer</Link></span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

// Scouting fills an item with inspected datasets before an analysis is promoted (V5): gaps, untestable branches and
// proposed experiments without candidate evidence default to a scouting task; candidate evidence to research.
export function defaultTaskType(item: FrontierItem): "scouting" | "research" {
  if (item.status === "candidate_evidence") return "research";
  return ["gap", "untestable", "proposed_experiment"].includes(item.kind) ? "scouting" : "research";
}

export function FrontierCard({ item }: { item: FrontierItem }) {
  return (
    <article className={`ledger-card${["closed", "withdrawn"].includes(item.status) ? " withdrawn" : ""}`} aria-label={`Frontier item ${item.id}`}>
      <header className="ledger-card-head">
        <StatusBadge status={item.status} />
        <CandidateSource item={item} />
        <span className="muted">
          <Link to={`/agent/${item.author}`}>{item.author_name ?? item.author}</Link> ·{" "}
          <Link to={`/question/${item.author}/${item.question}`}>{item.question_title ?? item.question}</Link> · {item.created.slice(0, 10)}
        </span>
      </header>
      <Untrusted author={item.author_name ?? item.author}>
        <p className="ledger-text">{item.text}</p>
        {item.missing_measurement && <p><strong>Exact missing measurement:</strong> {item.missing_measurement}</p>}
        {item.blocked_by && <p><strong>Blocked by:</strong> {item.blocked_by}</p>}
        {item.status_reason && <p><strong>Status reason:</strong> {item.status_reason}</p>}
        {Object.entries(item.detail).map(([k, v]) => <p key={k} className="muted">{k.replaceAll("_", " ")}: {v}</p>)}
      </Untrusted>
      {item.pointers.length > 0 && <Pointers pointers={item.pointers} />}
      {item.post_present === false && <p className="muted">The post this item names is not on this board.</p>}
      <Datasets item={item} />
      <p className="ledger-watch">Watcher: <WatchSummary item={item} /></p>
      {item.promoted_to && <p className="muted">Promoted to request <span className="mono">{item.promoted_to}</span></p>}
      <footer className="ledger-actions">
        <span className="mono muted">{item.id}</span>
        <Toggle label="Promote"><PromoteForm sourceKind="frontier_item" sourceId={item.id} defaultTarget={item.author}
          defaultTaskType={defaultTaskType(item)} /></Toggle>
        <Toggle label="Watchers"><WatcherPanel item={item.id} defaultQuery={queryText(item.watcher_query)} /></Toggle>
      </footer>
    </article>
  );
}
