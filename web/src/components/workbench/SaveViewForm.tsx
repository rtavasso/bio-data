import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { SavedView } from "../../types/workbench";
import { explain } from "../participation/writes";
import { describeView } from "./ViewBar";
import { saveView } from "./workbench";

const split = (text: string) => text.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);

// Save a view (spec v2 V4): a question set, a participant set and a time window. The server records it once,
// keyed by the hash of its canonical JSON; the hash is the share token every screen accepts as ?view=.
export function SaveViewForm() {
  const [questions, setQuestions] = useState("");
  const [participants, setParticipants] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [saved, setSaved] = useState<SavedView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      setSaved(await saveView({ questions: split(questions), participants: split(participants),
        since: since ? new Date(since).toISOString() : null, until: until ? new Date(until).toISOString() : null }));
    } catch (reason) {
      setError(explain(reason));
    }
  };
  return (
    <form className="me-form wb-viewform" onSubmit={submit} aria-label="Save a view">
      <label className="me-field"><span className="me-label">Questions</span>
        <input value={questions} onChange={(e) => setQuestions(e.target.value)} placeholder="q_… q_…" /></label>
      <label className="me-field"><span className="me-label">Participants</span>
        <input value={participants} onChange={(e) => setParticipants(e.target.value)} placeholder="names or ids" /></label>
      <label className="me-field"><span className="me-label">Since</span>
        <input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} /></label>
      <label className="me-field"><span className="me-label">Until</span>
        <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
      <button>Save view</button>
      {error && <span className="error" role="alert">{error}</span>}
      {saved && (
        <p role="status">
          {saved.existing ? "Already saved" : "Saved"}: {describeView(saved)}. Share token <code className="mono">{saved.view}</code>{" "}
          · open on <Link to={`/board?view=${saved.view}`}>the board</Link>, <Link to={`/map?view=${saved.view}`}>the map</Link>{" "}
          or <Link to={`/question?view=${saved.view}`}>questions</Link>.
        </p>
      )}
    </form>
  );
}
