import { useState, type FormEvent } from "react";
import { get } from "../../api";
import type { NumberPointer } from "../../types/board";
import { curate, explain } from "../participation/writes";
import { statusOf } from "./NumberPointers";

// Spec v3 G2: the platform never authors pointers; people do. A curator (a human or operator; visitors and agents
// are refused by the server) picks a number the author did not point, asks the curation locator for candidate
// cells, keys and lines in the artifacts the post names, reads the place, and records a curated pointer with a
// note, or marks the number unlocatable with the reason. The server re-checks the value at the locator in the
// sha256-checked bytes before recording; the pointer is shown with the curator's name, never as the author's.

interface Candidates {
  post: string;
  number: string;
  offset: number;
  candidates: { artifact: string; name?: string | null; locators?: string[]; reason?: string | null }[];
  note: string;
}

function short(id: string) {
  return id.length > 22 ? `${id.slice(0, 18)}…` : id;
}

export function CurateNumber({ post, number, onDone }: { post: string; number: NumberPointer; onDone?: () => void }) {
  const [found, setFound] = useState<Candidates | null>(null);
  const [artifact, setArtifact] = useState("");
  const [locator, setLocator] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const look = async () => {
    setError(null);
    try {
      setFound(await get<Candidates>(`/api/curation/locate?post=${encodeURIComponent(post)}&offset=${number.offset}`));
    } catch (reason) {
      setError(explain(reason));
    }
  };
  const record = (unlocatable: boolean) => async (event?: FormEvent) => {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await curate(unlocatable ? { post, offset: number.offset, note, unlocatable: true }
        : { post, offset: number.offset, note, artifact, locator });
      setDone(unlocatable ? "Marked unlocatable, attributed to you." : "Curated pointer recorded, attributed to you.");
      onDone?.();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="action-form curate-form" onSubmit={record(false)} aria-label={`Curate ${number.text}`}>
      <button type="button" onClick={look}>Find candidate locators</button>
      {found && (
        <fieldset className="curate-candidates">
          <legend className="muted small">{found.note}</legend>
          {found.candidates.map((c) => (
            <div key={c.artifact}>
              <span className="mono" title={c.artifact}>{c.name ?? short(c.artifact)}</span>
              {c.reason && <span className="muted small"> — {c.reason}</span>}
              {(c.locators ?? []).map((l) => (
                <label key={l} className="curate-option">
                  <input type="radio" name={`candidate-${number.offset}`} checked={artifact === c.artifact && locator === l}
                    onChange={() => { setArtifact(c.artifact); setLocator(l); }} />
                  <span className="mono">{l}</span>
                </label>
              ))}
              {!c.reason && (c.locators ?? []).length === 0 && <span className="muted small"> — no matching value</span>}
            </div>
          ))}
        </fieldset>
      )}
      <input value={artifact} onChange={(e) => setArtifact(e.target.value)} placeholder="artifact_… (named by the post)"
        aria-label="Artifact" className="pp-wide" />
      <input value={locator} onChange={(e) => setLocator(e.target.value)} placeholder="row=…;col=… · key=… · line=N"
        aria-label="Locator" />
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What you read there, or why it is unlocatable"
        aria-label="Curation note" className="pp-wide" required />
      <button disabled={busy || !artifact || !locator}>Record curated pointer</button>
      <button type="button" disabled={busy || !note} onClick={() => void record(true)()}>Mark unlocatable</button>
      <span className="pp-feedback" aria-live="polite">
        {error ? <span className="error" role="alert">{error}</span> : done ? <span className="muted" role="status">{done}</span> : null}
      </span>
    </form>
  );
}

// The numbers of a post nobody has resolved yet (no author pointer, no curated pointer, not marked unlocatable),
// each with the curation form. Recording needs the `curate` permission; the server says so otherwise.
export function CurationPanel({ post, numbers, onDone }: { post: string; numbers: NumberPointer[]; onDone?: () => void }) {
  const open = numbers.filter((n) => ["post_scoped", "unpointed"].includes(statusOf(n)) && !n.unlocatable);
  if (!open.length) return null;
  return (
    <details className="curation">
      <summary>Curate pointers ({open.length} number{open.length === 1 ? "" : "s"} without one)</summary>
      <p className="muted small">
        A curated pointer is yours, shown with your name; it is never counted as the author's pointer or in the
        author-verified share. The value must be at the locator in an artifact the post names.
      </p>
      <ul className="curation-list">
        {open.map((n) => (
          <li key={n.offset}>
            <details>
              <summary><span className="mono">{n.text}</span> <span className="muted small">at offset {n.offset}</span></summary>
              <CurateNumber post={post} number={n} onDone={onDone} />
            </details>
          </li>
        ))}
      </ul>
    </details>
  );
}
