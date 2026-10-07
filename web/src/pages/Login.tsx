import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Health } from "../api";
import { withBase } from "../base";
import { explain, login, visitorSignIn } from "../components/participation/writes";
import { useApi } from "../useApi";
import "./me.css";

// Accounts mode (M7): a person exchanges an operator-issued token for an HttpOnly session cookie.
// The token is sent once and never stored by the page. Spec v3 V15: a public commons may also offer visitor
// sign-in with a display name (comment and mark only); the token it returns is shown once to sign in again later.

function VisitorSignIn({ onLogin }: { onLogin: () => void }) {
  const [name, setName] = useState("");
  const [affiliation, setAffiliation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const signed = await visitorSignIn({ display_name: name.trim(), affiliation: affiliation.trim() || undefined });
      setToken(signed.token);
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  if (token) {
    return (
      <div className="panel" role="status">
        <p>Signed in as a visitor. You can comment and mark; your acts are attributed to you.</p>
        <p className="muted small">To sign in again later, keep this token (it is shown once): <code>{token}</code></p>
        <button type="button" onClick={onLogin}>Continue</button>
      </div>
    );
  }
  return (
    <form className="action-form" onSubmit={submit} aria-label="Visitor sign-in">
      <label className="me-grow">
        <span className="me-label">Display name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} aria-label="Display name" />
      </label>
      <label>
        <span className="me-label">Affiliation (optional)</span>
        <input value={affiliation} onChange={(e) => setAffiliation(e.target.value)} aria-label="Affiliation" />
      </label>
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in as a visitor"}</button>
      {error && <span className="error" role="alert">{error}</span>}
    </form>
  );
}
export default function Login({ onLogin = () => window.location.assign(withBase("/me")) }: { onLogin?: () => void }) {
  const health = useApi<Health>("/api/health");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(token.trim());
      setToken("");
      onLogin();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  if (health.data?.mode === "local") {
    return (
      <section className="me-page">
        <h1>Log in</h1>
        <p className="muted">This commons runs in local single-user mode: no login is needed. <Link to="/me">Go to your page.</Link></p>
      </section>
    );
  }
  return (
    <section className="me-page login">
      <h1>Log in</h1>
      <p className="muted">Paste the token an operator issued to you (<code>bio commons token create NAME</code>). It is exchanged for a session cookie and not kept by this page.</p>
      <form className="action-form" onSubmit={submit}>
        <label className="me-grow">
          <span className="me-label">Token</span>
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} required autoComplete="off"
            spellCheck={false} className="me-grow" aria-label="Token" />
        </label>
        <button disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
        {error && <span className="error" role="alert">{error}</span>}
      </form>
      {health.data?.visitor_signin && (
        <>
          <h2>Visiting?</h2>
          <p className="muted">This public commons lets visitors comment and mark after signing in with a display name.</p>
          <VisitorSignIn onLogin={onLogin} />
        </>
      )}
    </section>
  );
}
