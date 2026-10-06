import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { post, query } from "../../api";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Untrusted } from "../Untrusted";
import type { Watcher, WatcherList, WatcherRun } from "../../types/discovery";
import "./discovery.css";

// Watchers on one frontier item (M5.2). A watcher re-runs a scoped discovery query on a cadence the
// operator schedules; new accessions become a notice to the item's author. Retrieval only: whether a hit
// fits the item stays the author's decision. Exported for the /frontier page.

const INTERVALS: [number, string][] = [
  [604800, "weekly"],
  [86400, "daily"],
  [2592000, "every 30 days"],
];

function every(seconds: number) {
  return INTERVALS.find(([s]) => s === seconds)?.[1] ?? `every ${Math.round(seconds / 3600)} h`;
}

function parseFilters(text: string): Record<string, string> {
  const filters: Record<string, string> = {};
  for (const part of text.split(",").map((p) => p.trim()).filter(Boolean)) {
    const at = part.indexOf("=");
    if (at < 1) throw new Error(`filter "${part}" must be FIELD=VALUE`);
    filters[part.slice(0, at).trim()] = part.slice(at + 1).trim();
  }
  return filters;
}

function Runs({ watcher }: { watcher: Watcher }) {
  const runs = useApi<{ items: WatcherRun[] }>(`/api/watchers/${encodeURIComponent(watcher.id)}/runs`);
  return (
    <div className="watcher-runs">
      <Status state={runs} />
      {runs.data && runs.data.items.length === 0 && <p className="muted">No runs yet; it runs at the next scheduled tick.</p>}
      <ol>
        {runs.data?.items.map((run) => {
          const fresh = new Set((run.receipt?.new ?? []).map((h) => h.accession));
          return (
            <li key={run.id}>
              <div className="watcher-run-head">
                <time dateTime={run.created}>{run.created.slice(0, 16).replace("T", " ")}</time>
                <span>{run.found.length} found · {fresh.size} new</span>
                {run.post && <Link to={`/post/${run.post}`}>notice</Link>}
                {run.receipt_blob && <span className="mono" title="Receipt blob (library)">receipt {run.receipt_blob.slice(0, 12)}…</span>}
              </div>
              {run.receipt?.warnings.length ? <p className="muted">Warnings: {run.receipt.warnings.join("; ")}</p> : null}
              {run.found.length > 0 && (
                <Untrusted author={`${run.provider} (provider metadata)`}>
                  <ul className="watcher-hits">
                    {run.found.map((hit) => (
                      <li key={hit.accession}>
                        <span className="mono">{hit.accession}</span>
                        {fresh.has(hit.accession) && <span className="badge">new</span>} {hit.title}
                      </li>
                    ))}
                  </ul>
                </Untrusted>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function AttachWatcher({ item, providers, onDone }: { item: string; providers: string[]; onDone?: () => void }) {
  const [text, setText] = useState("");
  const [provider, setProvider] = useState("europepmc");
  const [cadence, setCadence] = useState(604800);
  const [filters, setFilters] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post<Watcher>("/api/watchers", {
        item, provider, interval_seconds: cadence, query: { query: text, filters: parseFilters(filters) },
      });
      setText("");
      setFilters("");
      setDone(true);
      onDone?.();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form watcher-form" onSubmit={submit} aria-label="Attach a watcher query">
      <input value={text} onChange={(e) => setText(e.target.value)} required maxLength={1000}
        placeholder="Scoped discovery query, e.g. Schwann Nae1 knockdown RNA-seq" aria-label="Watcher query" />
      <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Provider">
        {(providers.length ? providers : ["europepmc"]).map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select value={cadence} onChange={(e) => setCadence(Number(e.target.value))} aria-label="Cadence">
        {INTERVALS.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
      </select>
      <input value={filters} onChange={(e) => setFilters(e.target.value)} placeholder="filters: FIELD=VALUE, …"
        aria-label="Literal filters on returned hits" />
      <button disabled={busy}>Attach watcher</button>
      {error && <span className="error" role="alert">{error}</span>}
      {done && !error && <span className="muted" role="status">Watcher attached; it runs at the next scheduled tick.</span>}
    </form>
  );
}

export function WatcherPanel({ item, canAttach = true }: { item: string; canAttach?: boolean }) {
  const list = useApi<WatcherList>(`/api/watchers${query({ item })}`);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const disable = async (id: string) => {
    setError(null);
    try {
      await post(`/api/watchers/${encodeURIComponent(id)}/disable`, {});
      list.reload();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };
  return (
    <section className="watcher-panel" aria-label="Watchers">
      <h3>Watchers</h3>
      <p className="muted small">Retrieval only: new accessions become a notice to the item's author, who decides applicability.</p>
      <Status state={list} />
      {error && <p className="error" role="alert">{error}</p>}
      {list.data && list.data.items.length === 0 && <p className="muted">No watcher query attached.</p>}
      <ul className="watcher-list">
        {list.data?.items.map((w) => (
          <li key={w.id} className={w.enabled ? "" : "disabled"}>
            <div className="watcher-head">
              <strong>{w.provider}</strong> <q>{w.query.query}</q>
              {Object.keys(w.query.filters).length > 0 && (
                <span className="muted"> where {Object.entries(w.query.filters).map(([k, v]) => `${k}=${v}`).join(", ")}</span>
              )}
            </div>
            <div className="watcher-meta muted">
              <span>{w.enabled ? every(w.interval_seconds) : "disabled"}</span>
              {w.enabled && <span>next due {w.next_due_utc.slice(0, 10)}</span>}
              <span>{w.runs} run{w.runs === 1 ? "" : "s"}</span>
              {w.last_run && <span>last found {w.last_run.found}</span>}
              {w.last_run?.post && <Link to={`/post/${w.last_run.post}`}>latest notice</Link>}
            </div>
            <div className="watcher-actions">
              <button type="button" onClick={() => setOpen(open === w.id ? null : w.id)} aria-expanded={open === w.id}>
                {open === w.id ? "Hide runs" : "Runs"}
              </button>
              {w.enabled && <button type="button" onClick={() => disable(w.id)}>Disable</button>}
            </div>
            {open === w.id && <Runs watcher={w} />}
          </li>
        ))}
      </ul>
      {canAttach && <AttachWatcher item={item} providers={list.data?.providers ?? []} onDone={list.reload} />}
      {list.data && <p className="muted small">{list.data.cadence}</p>}
    </section>
  );
}

export default WatcherPanel;
