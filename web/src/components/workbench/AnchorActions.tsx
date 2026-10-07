import { useState, type FormEvent } from "react";
import type { Participant } from "../../api";
import { useApi } from "../../useApi";
import { explain, type Anchor } from "../participation/writes";
import { replyAtAnchor, requestReview } from "./workbench";
import "./workbench.css";

// Comment threads at anchors (spec v2 V4): a reply under an anchored comment is recorded with the same anchor
// (the server copies it from the thread's root comment) and names the post it answers.
export function ReplyBox({ comment, onDone, label = "Reply under this anchor" }: { comment: string; onDone?: () => void; label?: string }) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await replyAtAnchor(comment, body);
      setBody("");
      onDone?.();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="wb-reply" onSubmit={submit} aria-label={label}>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} required aria-label="Reply" placeholder="Your reply (attributed to you)" />
      <span><button disabled={busy || !body.trim()}>Reply</button>{error && <span className="error" role="alert"> {error}</span>}</span>
    </form>
  );
}

// "Request review" on an anchored claim: commissions an adversarial review (task type review) with the claim as
// subject and the anchor in the note, within the person's allowance. The anchor is a comment thread's (comment)
// or a passage/node anchor on the claim (anchor).
export function RequestReview({ claim, comment, anchor, onDone }: { claim: string; comment?: string; anchor?: Anchor; onDone?: () => void }) {
  const agents = useApi<{ items: Participant[] }>("/api/participants?kind=agent");
  const [target, setTarget] = useState("");
  const [minutes, setMinutes] = useState("30");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const request = await requestReview({ claim, target, budget: { minutes: Number(minutes) }, note: note || undefined,
        ...(comment ? { comment } : { anchor: anchor ?? { kind: "node", node_id: claim } }) });
      setMade(request.id);
      onDone?.();
    } catch (reason) {
      setError(explain(reason));
    }
  };
  return (
    <form className="wb-review" onSubmit={submit} aria-label="Request adversarial review">
      <label className="pp-field"><span>Reviewer</span>
        <select value={target} onChange={(e) => setTarget(e.target.value)} required aria-label="Reviewer">
          <option value="">choose…</option>
          {(agents.data?.items ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label className="pp-field"><span>Minutes</span>
        <input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} required /></label>
      <label className="pp-field"><span>Note (optional)</span><input value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <button>Request review</button>
      {made && <span role="status" className="muted">Review commissioned ({made}).</span>}
      {error && <span className="error" role="alert">{error}</span>}
    </form>
  );
}
