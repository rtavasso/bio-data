import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, post } from "../../api";
import { Untrusted } from "../Untrusted";
import { MarkForm, PromoteForm } from "../participation/Actions";
import type { Claim, FrontierItem, Pointer } from "../../types/ledger";

// Shared pieces of the claim ledger and frontier screens. Every author-stated string renders inside
// <Untrusted>; pointers link to the records they name and say when a named record is absent.

export function PointerLink({ pointer }: { pointer: Pointer }) {
  const missing = pointer.present === false ? <span className="ledger-badge bad"> missing</span> : null;
  const short = pointer.id.length > 24 ? `${pointer.id.slice(0, 20)}…` : pointer.id;
  let target: ReactNode = <span className="mono">{short}</span>;
  if (pointer.kind === "post" || (pointer.kind === "locator" && pointer.id.startsWith("post_"))) {
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

function Toggle({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="ledger-toggle">
      <button type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>{label}</button>
      {open && <div className="ledger-toggle-body">{children}</div>}
    </span>
  );
}

export function ClaimCard({ claim, onChange }: { claim: Claim; onChange?: () => void }) {
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
        <span className="mono muted">{claim.id}</span>
        <Toggle label="Mark"><MarkForm targetKind="claim" targetId={claim.id} onDone={onChange} /></Toggle>
      </footer>
    </article>
  );
}

// POST /api/watchers is implemented by the discovery area; a server without the route answers 404
// (unknown_endpoint from the SPA fallback, or FastAPI's plain Not Found) or 405.
export function watchersUnavailable(reason: unknown): boolean {
  if (!(reason instanceof ApiError)) return false;
  return reason.status === 405 || (reason.status === 404 && ["unknown_endpoint", "request_failed"].includes(reason.reason));
}

export function WatcherForm({ item, defaultQuery }: { item: string; defaultQuery?: string }) {
  const [query, setQuery] = useState(defaultQuery ?? "");
  const [provider, setProvider] = useState("geo");
  const [days, setDays] = useState("7");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await post("/api/watchers", { item, query, provider, interval_seconds: Number(days) * 86400 });
      setMessage({ ok: true, text: "Watcher attached; it retrieves, the author judges applicability." });
    } catch (reason) {
      setMessage({ ok: false, text: watchersUnavailable(reason) ? "Watchers are not available on this server yet." : (reason as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form" onSubmit={submit}>
      <input value={query} onChange={(e) => setQuery(e.target.value)} required placeholder="Scoped discovery query" aria-label="Watcher query" />
      <input value={provider} onChange={(e) => setProvider(e.target.value)} required aria-label="Provider" style={{ width: "7em" }} />
      <label>every <input type="number" min={1} value={days} onChange={(e) => setDays(e.target.value)} style={{ width: "4em" }} aria-label="Interval in days" /> days</label>
      <button disabled={busy}>Attach watcher</button>
      {message && <span className={message.ok ? "muted" : "error"} role={message.ok ? "status" : "alert"}>{message.text}</span>}
    </form>
  );
}

function queryText(query: FrontierItem["watcher_query"]): string | undefined {
  if (!query) return undefined;
  if (typeof query === "string") return query;
  return typeof query.text === "string" ? query.text : JSON.stringify(query);
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

export function FrontierCard({ item }: { item: FrontierItem }) {
  return (
    <article className={`ledger-card${["closed", "withdrawn"].includes(item.status) ? " withdrawn" : ""}`} aria-label={`Frontier item ${item.id}`}>
      <header className="ledger-card-head">
        <StatusBadge status={item.status} />
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
      <p className="ledger-watch">Watcher: <WatchSummary item={item} /></p>
      {item.promoted_to && <p className="muted">Promoted to request <span className="mono">{item.promoted_to}</span></p>}
      <footer className="ledger-actions">
        <span className="mono muted">{item.id}</span>
        <Toggle label="Promote"><PromoteForm sourceKind="frontier_item" sourceId={item.id} defaultTarget={item.author} /></Toggle>
        <Toggle label="Attach a watcher query"><WatcherForm item={item.id} defaultQuery={queryText(item.watcher_query)} /></Toggle>
      </footer>
    </article>
  );
}
