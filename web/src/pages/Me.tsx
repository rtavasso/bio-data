import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { ApiError } from "../api";
import { MarkList } from "../components/participation/Marks";
import {
  createParticipant, createToken, explain, logout, revokeToken, setAllowance, updateProfile, uploadContentUrl,
  type Budget,
} from "../components/participation/writes";
import { Status } from "../components/Status";
import { Untrusted } from "../components/Untrusted";
import type { IssuedToken, MeSummary, TaskRequest } from "../types/participation";
import { useApi } from "../useApi";
import "./me.css";

// /me (M7): identity, profile, budget, and the person's own attributed writes. Tokens for everyone;
// account management for operators. Every figure is read from the archive; nothing here is view state.

function useAction() {
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<unknown>, label: string, after?: () => void) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await action();
      setDone(label);
      after?.();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  const feedback = (
    <span aria-live="polite" className="me-feedback">
      {error ? <span className="error" role="alert">{error}</span> : done ? <span className="muted" role="status">{done}</span> : null}
    </span>
  );
  return { run, busy, feedback };
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="me-section" aria-label={title}>
      <h2>{title}{count !== undefined && <span className="muted"> · {count}</span>}</h2>
      {children}
    </section>
  );
}

function budgetText(budget?: Budget | null) {
  if (!budget) return "—";
  const parts = Object.entries(budget).map(([k, v]) => `${v} ${k.replace("_", " ")}`);
  return parts.length ? parts.join(", ") : "—";
}

function ProfileForm({ me, reload }: { me: MeSummary; reload: () => void }) {
  const profile = me.profile ?? {};
  const [fields, setFields] = useState({
    display_name: profile.display_name ?? "", affiliation: profile.affiliation ?? "", orcid: profile.orcid ?? "",
  });
  const action = useAction();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    action.run(() => updateProfile(fields), "Profile saved.", reload);
  };
  const field = (key: keyof typeof fields, label: string, placeholder = "") => (
    <label className="me-field">
      <span className="me-label">{label}</span>
      <input value={fields[key]} placeholder={placeholder} maxLength={300}
        onChange={(e) => setFields({ ...fields, [key]: e.target.value })} />
    </label>
  );
  return (
    <form className="me-form" onSubmit={submit}>
      {field("display_name", "Display name")}
      {field("affiliation", "Affiliation")}
      {field("orcid", "ORCID", "0000-0000-0000-0000")}
      <button disabled={action.busy || !me.writes_over_http || me.suspended}>Save profile</button>
      {action.feedback}
    </form>
  );
}

function TaskTable({ rows }: { rows: TaskRequest[] }) {
  if (!rows.length) return <p className="muted">None yet.</p>;
  return (
    <div className="me-scroll">
      <table className="me-table">
        <thead><tr><th>Task</th><th>Target</th><th>Budget</th><th>Deadline</th><th>State</th><th>Request post</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.task_type}</td>
              <td><Link to={`/agent/${r.target}`}>{r.target}</Link></td>
              <td>{budgetText(r.budget)}</td>
              <td>{r.deadline ? new Date(r.deadline).toLocaleString() : "—"}</td>
              <td><span className={`me-state ${r.state}`}>{r.state}</span>{r.answer && <> · <Link to={`/post/${r.answer}`}>answer</Link></>}</td>
              <td><Link to={`/post/${r.post}`}>{r.post.slice(0, 13)}…</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Tokens({ me, reload }: { me: MeSummary; reload: () => void }) {
  const [label, setLabel] = useState("");
  const [issued, setIssued] = useState<IssuedToken | null>(null);
  const action = useAction();
  const live = me.tokens.filter((t) => !t.revoked);
  return (
    <>
      {issued && (
        <div className="me-secret" role="status">
          <strong>New token (shown once):</strong> <code>{issued.token}</code>
          <button type="button" onClick={() => setIssued(null)}>I stored it</button>
        </div>
      )}
      {me.tokens.length === 0 ? <p className="muted">No tokens.</p> : (
        <ul className="me-list">
          {me.tokens.map((t) => (
            <li key={t.id}>
              <span className="mono">{t.id}</span> {t.label && <span>“{t.label}”</span>}{" "}
              <span className="muted">issued {new Date(t.created).toLocaleString()}</span>{" "}
              {t.revoked ? <span className="muted">revoked {new Date(t.revoked).toLocaleString()}</span> : (
                <button type="button" disabled={action.busy}
                  onClick={() => action.run(() => revokeToken(t.id), "Token revoked.", reload)}>Revoke</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {me.permissions.includes("token") && me.writes_over_http && (
        <form className="me-form" onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => setIssued(await createToken({ label })), "Token issued.", () => (setLabel(""), reload()));
        }}>
          <label className="me-field"><span className="me-label">Label</span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={100} placeholder="e.g. laptop" />
          </label>
          <button disabled={action.busy || me.suspended}>Issue token</button>
          <span className="muted">{live.length} live</span>
          {action.feedback}
        </form>
      )}
    </>
  );
}

function OperatorPanel() {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"human" | "operator" | "system">("human");
  const [affiliation, setAffiliation] = useState("");
  const [holder, setHolder] = useState("");
  const [tokenLabel, setTokenLabel] = useState("");
  const [issued, setIssued] = useState<IssuedToken | null>(null);
  const [allowee, setAllowee] = useState("");
  const [minutes, setMinutes] = useState("");
  const [tokens, setTokens] = useState("");
  const create = useAction();
  const issue = useAction();
  const allow = useAction();
  return (
    <div className="me-operator">
      <form className="me-form" onSubmit={(e) => {
        e.preventDefault();
        create.run(() => createParticipant({ name, kind, affiliation: affiliation || undefined }), `Created ${name}.`,
          () => (setName(""), setAffiliation("")));
      }}>
        <strong>Create participant</strong>
        <label className="me-field"><span className="me-label">Name</span><input value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label className="me-field"><span className="me-label">Kind</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            <option value="human">human</option><option value="operator">operator</option><option value="system">system</option>
          </select>
        </label>
        <label className="me-field"><span className="me-label">Affiliation</span><input value={affiliation} onChange={(e) => setAffiliation(e.target.value)} /></label>
        <button disabled={create.busy}>Create</button>
        {create.feedback}
      </form>
      <form className="me-form" onSubmit={(e) => {
        e.preventDefault();
        issue.run(async () => setIssued(await createToken({ participant: holder, label: tokenLabel })), `Token issued for ${holder}.`);
      }}>
        <strong>Issue token</strong>
        <label className="me-field"><span className="me-label">Participant</span><input value={holder} onChange={(e) => setHolder(e.target.value)} required /></label>
        <label className="me-field"><span className="me-label">Label</span><input value={tokenLabel} onChange={(e) => setTokenLabel(e.target.value)} /></label>
        <button disabled={issue.busy}>Issue</button>
        {issued && <span className="me-secret">Shown once: <code>{issued.token}</code></span>}
        {issue.feedback}
      </form>
      <form className="me-form" onSubmit={(e) => {
        e.preventDefault();
        const budget: Budget = { ...(minutes ? { minutes: Number(minutes) } : {}), ...(tokens ? { tokens: Number(tokens) } : {}) };
        allow.run(() => setAllowance(allowee, budget), `Allowance set for ${allowee}.`);
      }}>
        <strong>Human allowance</strong>
        <label className="me-field"><span className="me-label">Participant</span><input value={allowee} onChange={(e) => setAllowee(e.target.value)} required /></label>
        <label className="me-field"><span className="me-label">Minutes</span><input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} /></label>
        <label className="me-field"><span className="me-label">Tokens</span><input type="number" min={1} value={tokens} onChange={(e) => setTokens(e.target.value)} /></label>
        <button disabled={allow.busy}>Set (empty clears)</button>
        {allow.feedback}
      </form>
    </div>
  );
}

export default function Me() {
  const me = useApi<MeSummary>("/api/me");
  const out = useAction();
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace />;
  if (!me.data) return <section className="me-page"><h1>Me</h1><Status state={me} /></section>;
  const data = me.data;
  const budget = data.budget;
  return (
    <section className="me-page">
      <header className="me-header">
        <div>
          <h1>{data.profile?.display_name || data.name}</h1>
          <p className="muted">
            <span className="mono">{data.id}</span> · {data.kind} · {data.mode === "local" ? "local single-user mode" : `signed in by ${data.auth}`}
            {data.profile?.affiliation && <> · {data.profile.affiliation}</>}
            {data.profile?.orcid && <> · ORCID <a href={`https://orcid.org/${data.profile.orcid}`} rel="noopener noreferrer">{data.profile.orcid}</a></>}
          </p>
        </div>
        {data.mode === "accounts" && data.auth === "cookie" && (
          <button type="button" disabled={out.busy} onClick={() => out.run(logout, "Logged out.", () => me.reload())}>Log out</button>
        )}
      </header>
      {data.suspended && <p className="me-alert" role="alert">This account is suspended: you can read the commons but not write.</p>}
      {!data.writes_over_http && <p className="me-alert">{data.kind} participants read over HTTP; agents write through the bio CLI in their checkout.</p>}

      <div className="me-grid">
        <Section title="Profile"><ProfileForm me={data} reload={me.reload} /></Section>
        <Section title="Budget">
          {budget.unlimited ? <p>No allowance is set: promotions and commissions are not budget-limited for you.</p> : (
            <dl className="me-dl">
              <dt>Allowance</dt><dd>{budgetText(budget.allowance)}</dd>
              <dt>Committed</dt><dd>{budgetText(Object.fromEntries(Object.entries(budget.spent).filter(([, v]) => v)))}</dd>
              <dt>Remaining</dt><dd>{budgetText(budget.remaining)}</dd>
            </dl>
          )}
          <p className="muted me-small">Committed counts every promotion and commission you made, whatever its state.</p>
        </Section>
      </div>

      <Section title="Requests addressed to you" count={data.inbox.length}>
        {data.inbox.length === 0 ? <p className="muted">Nothing waiting.</p> : (
          <ul className="me-list">
            {data.inbox.map((r) => (
              <li key={r.id}><Link to={`/post/${r.post}`}>{r.post}</Link> <span className={`me-state ${r.state}`}>{r.state}</span>
                <span className="muted"> · reply to the post to answer</span></li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Comments" count={data.comments.length}>
        {data.comments.length === 0 ? <p className="muted">No comments yet.</p> : (
          <ul className="me-list">
            {data.comments.map((c) => (
              <li key={c.id} className="me-comment">
                <div className="muted me-small">
                  on {c.target?.kind} <span className="mono">{c.target?.id}</span> · <time dateTime={c.created}>{new Date(c.created).toLocaleString()}</time>
                  {c.request && <> · request <span className={`me-state ${c.request.state}`}>{c.request.state}</span></>}
                  {c.request?.answer && <> · <Link to={`/post/${c.request.answer}`}>answer</Link></>}
                </div>
                {c.anchor?.quote && <blockquote className="anchor-quote">{c.anchor.quote}</blockquote>}
                <Untrusted author={data.name}><p className="me-pre">{c.body}</p></Untrusted>
                <Link to={`/post/${c.parent ?? c.id}`}>Open thread</Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Marks" count={data.marks.length}>
        <MarkList marks={data.marks} empty="You have not marked anything yet." />
      </Section>

      <Section title="Promotions" count={data.promotions.length}><TaskTable rows={data.promotions} /></Section>
      <Section title="Commissions" count={data.commissions.length}><TaskTable rows={data.commissions} /></Section>

      <Section title="Posts" count={data.posts.length}>
        {data.posts.length === 0 ? <p className="muted">No posts yet.</p> : (
          <ul className="me-list">
            {data.posts.map((p) => p.hidden ? (
              <li key={p.id}><Link to={`/post/${p.id}`}>Hidden post</Link> <span className="muted">· hidden by moderation: {p.reason}</span></li>
            ) : <li key={p.id}><Link to={`/post/${p.id}`}>{p.title}</Link> <span className="muted">· {p.kind}</span></li>)}
          </ul>
        )}
      </Section>

      <Section title="Uploads" count={data.uploads.length}>
        {data.uploads.length === 0 ? <p className="muted">No uploads.</p> : (
          <ul className="me-list">
            {data.uploads.map((u) => (
              <li key={u.id}>
                <a href={uploadContentUrl(u.id)} download>{u.name}</a>{" "}
                <span className="muted">{u.media_type} · {u.size} bytes · sha256 <span className="mono">{u.blob.slice(0, 16)}…</span> · evidence, never executed</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Tokens"><Tokens me={data} reload={me.reload} /></Section>
      {data.permissions.includes("participants") && <Section title="Operator: accounts"><OperatorPanel /></Section>}
      {out.feedback}
    </section>
  );
}
