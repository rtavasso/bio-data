import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError, query } from "../api";
import { Status } from "../components/Status";
import { explain } from "../components/participation/writes";
import { grantMember, revokeMember } from "../components/workbench/workbench";
import type { AccessStanding, AuditPage, Membership } from "../types/workbench";
import { useApi } from "../useApi";
import "../components/workbench/workbench.css";

// /audit (spec v2 V9): the operator's view of the immutable board event log, filtered by kind, participant and
// time, newest first, paged by sequence; and the membership of a private commons. Operator only: the server
// refuses everyone else (GET /api/audit needs the `audit` permission).

function Members() {
  const access = useApi<AccessStanding>("/api/access");
  const list = useApi<{ read_policy: string; items: Membership[] }>("/api/members");
  const [who, setWho] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const act = async (event: FormEvent, action: "grant" | "revoke") => {
    event.preventDefault();
    setError(null);
    try {
      await (action === "grant" ? grantMember(who, reason) : revokeMember(who, reason));
      list.reload();
    } catch (reason) {
      setError(explain(reason));
    }
  };
  return (
    <section className="panel" aria-label="Membership">
      <h2>Read policy and membership</h2>
      <p className="meta">
        Read policy: <strong>{access.data?.read ?? "…"}</strong> ({access.data?.note}). Set it in{" "}
        <code>commons.toml</code> <code>[access] read</code>; operators always read.
      </p>
      {list.data && (list.data.items.length === 0 ? <p className="muted">No membership records.</p> : (
        <ul>
          {list.data.items.map((m) => (
            <li key={m.participant}>{m.name} <span className="muted">({m.kind})</span> · {m.state} · {m.reason || "no reason"}
              <span className="muted"> · {m.updated}</span></li>
          ))}
        </ul>
      ))}
      <form className="wb-filters" onSubmit={(e) => act(e, "grant")}>
        <label className="pp-field"><span>Participant</span><input value={who} onChange={(e) => setWho(e.target.value)} required /></label>
        <label className="pp-field"><span>Reason</span><input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button>Grant</button>
        <button type="button" onClick={(e) => act(e as unknown as FormEvent, "revoke")}>Revoke</button>
        {error && <span className="error" role="alert">{error}</span>}
      </form>
    </section>
  );
}

export default function Audit() {
  const [kind, setKind] = useState("");
  const [participant, setParticipant] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [before, setBefore] = useState<number | null>(null);
  const [applied, setApplied] = useState({ kind: "", participant: "", since: "", until: "" });
  const path = "/api/audit" + query({ ...applied, since: applied.since && new Date(applied.since).toISOString(),
    until: applied.until && new Date(applied.until).toISOString(), before, limit: 100 });
  const page = useApi<AuditPage>(path);
  if (page.error instanceof ApiError && page.error.status === 401) return <Navigate to="/login" replace />;
  if (page.error instanceof ApiError && page.error.status === 403) {
    return <section><h1>Audit log</h1><p className="error">The audit log is for operators.</p></section>;
  }
  const data = page.data;
  return (
    <section className="wb-audit">
      <h1>Audit log</h1>
      <form className="wb-filters" onSubmit={(e) => {
        e.preventDefault();
        setBefore(null);
        setApplied({ kind, participant, since, until });
      }}>
        <label className="pp-field"><span>Kind</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Event kind">
            <option value="">all kinds</option>
            {(data?.kinds ?? []).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label className="pp-field"><span>Participant</span><input value={participant} onChange={(e) => setParticipant(e.target.value)} /></label>
        <label className="pp-field"><span>Since</span><input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} /></label>
        <label className="pp-field"><span>Until</span><input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        <button>Filter</button>
      </form>
      {!data ? <Status state={page} /> : (
        <>
          <p className="meta">
            {data.total} events match · {Object.entries(data.facets).slice(0, 8).map(([k, n]) => `${k} ${n}`).join(" · ")}
            {data.login_failures_recorded !== null && <> · {data.login_failures_recorded} failed logins on record</>}
          </p>
          <table aria-label="Board events">
            <thead><tr><th scope="col">Seq</th><th scope="col">Kind</th><th scope="col">Time</th><th scope="col">Body</th></tr></thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.seq}>
                  <td className="mono">{e.seq}</td>
                  <td>{e.kind}{e.redacted && <span className="muted small"> ({e.redacted})</span>}</td>
                  <td className="small">{e.created}</td>
                  <td><pre>{JSON.stringify(e.body, null, 1)}</pre></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            {before !== null && <button type="button" onClick={() => setBefore(null)}>Newest</button>}{" "}
            {data.next_before !== null && <button type="button" onClick={() => setBefore(data.next_before)}>Older</button>}
          </p>
        </>
      )}
      <Members />
    </section>
  );
}
