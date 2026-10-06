import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Health } from "../api";
import { withBase } from "../base";
import { explain, login } from "../components/participation/actions";
import { useApi } from "../useApi";
import "./me.css";

// Accounts mode (M7): a person exchanges an operator-issued token for an HttpOnly session cookie.
// The token is sent once and never stored by the page.
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
    </section>
  );
}
