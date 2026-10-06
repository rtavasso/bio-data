import { useState, type FormEvent } from "react";
import type { MeSummary } from "../../types/participation";
import { useApi } from "../../useApi";
import { explain, moderateParticipant, moderatePost } from "./writes";

// Operator moderation (M2.8): hide/unhide a post, suspend/reinstate a participant. Shown only to callers
// whose permissions include the action; the server checks again. Every action is event-logged with a
// public reason and is reversible; nothing is deleted.

function useCan(action: string) {
  const me = useApi<MeSummary>("/api/me");
  return Boolean(me.data?.permissions?.includes(action));
}

function ReasonForm({ label, verb, onSubmit, onDone }: {
  label: string; verb: string; onSubmit: (reason: string) => Promise<unknown>; onDone?: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await onSubmit(reason);
      setReason("");
      setDone(true);
      onDone?.();
    } catch (failure) {
      setError(explain(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form" onSubmit={submit} aria-label={label}>
      <input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={2000} className="pp-wide"
        aria-label="Public reason" placeholder="Reason (recorded publicly)" />
      <button disabled={busy}>{verb}</button>
      <span className="pp-feedback" aria-live="polite">
        {error ? <span className="error" role="alert">{error}</span> : done ? <span className="muted" role="status">Recorded.</span> : null}
      </span>
    </form>
  );
}

export function ModeratePost({ post, hidden, onDone }: { post: string; hidden: boolean; onDone?: () => void }) {
  if (!useCan("hide")) return null;
  const action = hidden ? "unhide" : "hide";
  return (
    <details>
      <summary>{hidden ? "Unhide (operator)" : "Hide (operator)"}</summary>
      <p className="muted">Hiding keeps the post's identity, author and bytes; readers see the reason instead of the content.</p>
      <ReasonForm label={`${action} post`} verb={hidden ? "Unhide" : "Hide"} onDone={onDone}
        onSubmit={(reason) => moderatePost(action, { post, reason })} />
    </details>
  );
}

export function ModerateParticipant({ participant, onDone }: { participant: string; onDone?: () => void }) {
  const [action, setAction] = useState<"suspend" | "reinstate">("suspend");
  if (!useCan("suspend")) return null;
  return (
    <details>
      <summary>Suspend or reinstate (operator)</summary>
      <p className="muted">A suspended participant can read but not write; operators cannot be suspended.</p>
      <select value={action} onChange={(e) => setAction(e.target.value as "suspend" | "reinstate")} aria-label="Moderation action">
        <option value="suspend">suspend</option>
        <option value="reinstate">reinstate</option>
      </select>
      <ReasonForm label={`${action} participant`} verb={action === "suspend" ? "Suspend" : "Reinstate"} onDone={onDone}
        onSubmit={(reason) => moderateParticipant(action, { participant, reason })} />
    </details>
  );
}
