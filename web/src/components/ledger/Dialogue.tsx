import { Link } from "react-router-dom";
import { Untrusted } from "../Untrusted";
import type { DialogueThread } from "../../types/ledger";

// Spec v3 V12: the exchange at an anchor, shown next to the claim. Every post is attributed, untrusted text; a
// disputed mark opens a thread with the person's own note; the author's reply resolves nothing by itself.
export function Dialogue({ threads }: { threads: DialogueThread[] }) {
  if (!threads.length) return null;
  return (
    <section className="ledger-dialogue" aria-label="Dialogue">
      {threads.map((t) => t.hidden ? (
        <p key={t.thread} className="muted">A thread hidden by moderation: {t.reason ?? "no reason recorded"}.</p>
      ) : (
        <div key={t.thread} className="ledger-thread">
          <p className="muted small">
            Thread <Link to={`/post/${t.thread}`} className="mono">{t.thread.slice(0, 14)}…</Link>
            {t.opened_by_dispute ? " opened by a disputed mark" : " at an anchor"} · {t.replies ?? 0} repl{t.replies === 1 ? "y" : "ies"}
            {t.awaiting_author ? " · awaiting the author" : ""}
          </p>
          <ol className="ledger-thread-posts">
            {(t.posts ?? []).map((p) => p.hidden ? (
              <li key={p.post} className="muted">A post hidden by moderation: {p.reason ?? "no reason recorded"}.</li>
            ) : (
              <li key={p.post}>
                <span className="small">
                  <Link to={`/agent/${p.participant}`}>{p.participant_name ?? p.participant}</Link>{" "}
                  <span className="muted">({p.participant_kind}{p.participant === t.target_author ? ", author" : ""})</span>
                </span>
                <Untrusted author={p.participant_name ?? p.participant}><p className="ledger-text">{p.text}</p></Untrusted>
                {(p.claims ?? []).length > 0 && (
                  <ul className="small" aria-label="Claims in this reply">
                    {(p.claims ?? []).map((c) => (
                      <li key={c.id}><span className="ledger-badge">{c.status}</span> <Untrusted>{c.text}</Untrusted></li>
                    ))}
                  </ul>
                )}
                {(p.artifacts ?? []).length > 0 && (
                  <p className="small">{(p.artifacts ?? []).map((a) => <Link key={a} to={`/artifact/${a}`} className="mono">{a.slice(0, 18)}… </Link>)}</p>
                )}
              </li>
            ))}
          </ol>
          <p className="muted small">
            <Link to={`/post/${t.post ?? t.thread}`}>Reply at the anchor</Link>; a reply changes no claim, mark or request status.
          </p>
        </div>
      ))}
    </section>
  );
}
