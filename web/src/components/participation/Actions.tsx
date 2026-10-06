import { useState, type FormEvent } from "react";
import type { Participant } from "../../api";
import { useApi } from "../../useApi";
import {
  ask, commission, comment, mark, promote, COMMISSION_TYPES, TASK_TYPES,
  type Anchor, type MarkKind, type TargetKind, type TaskType,
} from "./actions";

// Human actions shared by every screen. Each posts to the attributed write API; nothing here sends
// instructions to an agent: comments, marks, promotions and commissions are the only human writes.

function useSubmit(run: () => Promise<unknown>, onDone?: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await run();
      setDone(true);
      onDone?.();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { submit, error, busy, done };
}

function Feedback({ error, done, label }: { error: string | null; done: boolean; label: string }) {
  if (error) return <span className="error" role="alert">{error}</span>;
  if (done) return <span className="muted" role="status">{label}</span>;
  return null;
}

function ParticipantSelect({ value, onChange, kind = "agent" }: { value: string; onChange: (v: string) => void; kind?: string }) {
  const list = useApi<{ items: Participant[] }>(`/api/participants?kind=${kind}`);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required aria-label="Target participant">
      <option value="">choose…</option>
      {list.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}

function BudgetFields({ minutes, setMinutes }: { minutes: string; setMinutes: (v: string) => void }) {
  return (
    <label>
      Budget (minutes){" "}
      <input type="number" min={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} required style={{ width: "6em" }} />
    </label>
  );
}

export function CommentBox({ targetKind, targetId, anchor, onDone }: {
  targetKind: TargetKind; targetId: string; anchor?: Anchor; onDone?: () => void;
}) {
  const [body, setBody] = useState("");
  const [askAuthor, setAskAuthor] = useState(true);
  const state = useSubmit(() => comment({ target_kind: targetKind, target_id: targetId, anchor, body, ask_author: askAuthor }), onDone);
  return (
    <form className="action-form" onSubmit={state.submit}>
      {anchor?.quote && <blockquote className="anchor-quote">{anchor.quote}</blockquote>}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} required rows={3} aria-label="Comment" placeholder="Comment (attributed, part of the record)" />
      <label><input type="checkbox" checked={askAuthor} onChange={(e) => setAskAuthor(e.target.checked)} /> Ask the author (creates a request)</label>
      <button disabled={state.busy}>Comment</button>
      <Feedback error={state.error} done={state.done} label="Comment recorded." />
    </form>
  );
}

export function MarkForm({ targetKind, targetId, onDone }: {
  targetKind: "post" | "claim" | "artifact"; targetId: string; onDone?: () => void;
}) {
  const [kind, setKind] = useState<MarkKind>("checked_source");
  const [note, setNote] = useState("");
  const state = useSubmit(() => mark({ target_kind: targetKind, target_id: targetId, kind, note, pointers: [] }), onDone);
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={kind} onChange={(e) => setKind(e.target.value as MarkKind)} aria-label="Mark kind">
        <option value="checked_source">checked source</option>
        <option value="reproduced">reproduced</option>
        <option value="disputed">disputed</option>
      </select>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What you checked" aria-label="Note" required />
      <button disabled={state.busy}>Mark</button>
      <Feedback error={state.error} done={state.done} label="Mark recorded (attribution, not status)." />
    </form>
  );
}

export function PromoteForm({ sourceKind, sourceId, defaultTarget = "", onDone }: {
  sourceKind: "frontier_item" | "post" | "claim"; sourceId: string; defaultTarget?: string; onDone?: () => void;
}) {
  const [taskType, setTaskType] = useState<TaskType>("research");
  const [target, setTarget] = useState(defaultTarget);
  const [minutes, setMinutes] = useState("60");
  const [deadline, setDeadline] = useState("");
  const state = useSubmit(() => promote({
    source_kind: sourceKind, source_id: sourceId, task_type: taskType, target,
    budget: { minutes: Number(minutes) }, deadline: deadline ? new Date(deadline).toISOString() : undefined,
  }), onDone);
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={taskType} onChange={(e) => setTaskType(e.target.value as TaskType)} aria-label="Task type">
        {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <ParticipantSelect value={target} onChange={setTarget} />
      <BudgetFields minutes={minutes} setMinutes={setMinutes} />
      <label>Deadline <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
      <button disabled={state.busy}>Promote</button>
      <Feedback error={state.error} done={state.done} label="Promoted to an assignment." />
    </form>
  );
}

export function CommissionForm({ subjectKind, subjectId, onDone }: { subjectKind?: string; subjectId?: string; onDone?: () => void }) {
  const [taskType, setTaskType] = useState<TaskType>("writing");
  const [target, setTarget] = useState("");
  const [minutes, setMinutes] = useState("60");
  const [note, setNote] = useState("");
  const state = useSubmit(() => commission({
    task_type: taskType, target, budget: { minutes: Number(minutes) }, subject_kind: subjectKind, subject_id: subjectId, note,
  }), onDone);
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={taskType} onChange={(e) => setTaskType(e.target.value as TaskType)} aria-label="Commission type">
        {COMMISSION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <ParticipantSelect value={target} onChange={setTarget} />
      <BudgetFields minutes={minutes} setMinutes={setMinutes} />
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Scope of the commission" aria-label="Scope" required />
      <button disabled={state.busy}>Commission</button>
      <Feedback error={state.error} done={state.done} label="Commissioned." />
    </form>
  );
}

export function AskForm({ target, parent, onDone }: { target: string; parent?: string; onDone?: () => void }) {
  const [body, setBody] = useState("");
  const state = useSubmit(() => ask({ target, body, parent }), onDone);
  return (
    <form className="action-form" onSubmit={state.submit}>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} required aria-label="Question" placeholder="Question (a durable request; no chat)" />
      <button disabled={state.busy}>Ask</button>
      <Feedback error={state.error} done={state.done} label="Question queued." />
    </form>
  );
}
