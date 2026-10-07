import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { Participant } from "../../api";
import type { Pointer, UploadRecord } from "../../types/participation";
import { useApi } from "../../useApi";
import {
  ask, commission, comment, createPost, explain, mark, promote, requestReplication, uploadFile, COMMISSION_TYPES,
  MARK_KINDS, TASK_TYPES,
  type Anchor, type Budget, type MarkKind, type TargetKind, type TaskType,
} from "./writes";
import "./participation.css";

// Human actions shared by every screen. Each posts to the attributed write API; nothing here sends
// instructions to an agent: posts, comments, marks, promotions and commissions are the only human writes,
// and the server records each one under the person's own identity.

function useSubmit(run: () => Promise<unknown>, onDone?: () => void, reset?: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await run();
      setDone(true);
      reset?.();
      onDone?.();
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
    }
  };
  return { submit, error, busy, done };
}

function Feedback({ error, done, label }: { error: string | null; done: boolean; label: string }) {
  return (
    <span className="pp-feedback" aria-live="polite">
      {error ? <span className="error" role="alert">{error}</span> : done ? <span className="muted" role="status">{label}</span> : null}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="pp-field"><span>{label}</span>{children}</label>;
}

function ParticipantSelect({ value, onChange, kind = "agent" }: { value: string; onChange: (v: string) => void; kind?: string }) {
  const list = useApi<{ items: Participant[] }>(`/api/participants?kind=${kind}`);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required aria-label="Target participant">
      <option value="">{list.loading ? "loading…" : "choose…"}</option>
      {(list.data?.items ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}

function useBudget(initialMinutes = "60") {
  const [minutes, setMinutes] = useState(initialMinutes);
  const [tokens, setTokens] = useState("");
  const budget = (): Budget => ({ minutes: Number(minutes), ...(tokens ? { tokens: Number(tokens) } : {}) });
  return { minutes, setMinutes, tokens, setTokens, budget };
}

function BudgetFields({ state }: { state: ReturnType<typeof useBudget> }) {
  return (
    <span className="pp-budget">
      <Field label="Minutes">
        <input type="number" min={1} step={1} value={state.minutes} onChange={(e) => state.setMinutes(e.target.value)} required />
      </Field>
      <Field label="Tokens (optional)">
        <input type="number" min={1} step={1} value={state.tokens} onChange={(e) => state.setTokens(e.target.value)} />
      </Field>
    </span>
  );
}

// "kind:id[:locator]" per line or comma, e.g. "artifact:artifact_…, post:post_…".
export function parsePointers(text: string): Pointer[] {
  return text
    .split(/[\n,]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [kind, id, ...rest] = part.split(":");
      return { kind, id: id ?? "", ...(rest.length ? { locator: rest.join(":") } : {}) };
    });
}

export function CommentBox({ targetKind, targetId, anchor, onDone }: {
  targetKind: TargetKind; targetId: string; anchor?: Anchor; onDone?: () => void;
}) {
  const [body, setBody] = useState("");
  const [askAuthor, setAskAuthor] = useState(true);
  const [minutes, setMinutes] = useState("15");
  const state = useSubmit(
    () => comment({ target_kind: targetKind, target_id: targetId, anchor, body, ask_author: askAuthor,
      ...(askAuthor ? { budget: { minutes: Number(minutes) } } : {}) }),
    onDone,
    () => setBody(""),
  );
  return (
    <form className="action-form" onSubmit={state.submit}>
      {anchor?.quote && <blockquote className="anchor-quote">{anchor.quote}</blockquote>}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} required rows={3} aria-label="Comment"
        placeholder="Comment (attributed, part of the record)" />
      <label><input type="checkbox" checked={askAuthor} onChange={(e) => setAskAuthor(e.target.checked)} /> Ask the author (creates a request)</label>
      {askAuthor && (
        <Field label="Ask budget (minutes)">
          <input type="number" min={1} step={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} required />
        </Field>
      )}
      <button disabled={state.busy}>{state.busy ? "Commenting…" : "Comment"}</button>
      <Feedback error={state.error} done={state.done} label={askAuthor ? "Comment recorded; the author has a request." : "Comment recorded."} />
    </form>
  );
}

export function MarkForm({ targetKind, targetId, onDone }: {
  targetKind: "post" | "claim" | "artifact"; targetId: string; onDone?: () => void;
}) {
  const [kind, setKind] = useState<MarkKind>("checked_source");
  const [note, setNote] = useState("");
  const [pointers, setPointers] = useState("");
  const state = useSubmit(
    () => mark({ target_kind: targetKind, target_id: targetId, kind, note, pointers: parsePointers(pointers) }),
    onDone,
    () => (setNote(""), setPointers("")),
  );
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={kind} onChange={(e) => setKind(e.target.value as MarkKind)} aria-label="Mark kind">
        {MARK_KINDS.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}
      </select>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What you checked" aria-label="Note" required />
      <input value={pointers} onChange={(e) => setPointers(e.target.value)} placeholder="Pointers: artifact:ID, post:ID"
        aria-label="Pointers" className="pp-wide" />
      <button disabled={state.busy}>Mark</button>
      <Feedback error={state.error} done={state.done} label="Mark recorded (attribution, not status)." />
    </form>
  );
}

export function PromoteForm({ sourceKind, sourceId, defaultTarget = "", defaultTaskType = "research", onDone }: {
  sourceKind: "frontier_item" | "post" | "claim" | "shared_experiment"; sourceId: string; defaultTarget?: string;
  defaultTaskType?: TaskType; onDone?: () => void;
}) {
  const [taskType, setTaskType] = useState<TaskType>(defaultTaskType);
  const [target, setTarget] = useState(defaultTarget);
  const [deadline, setDeadline] = useState("");
  const [note, setNote] = useState("");
  const budget = useBudget();
  const state = useSubmit(() => promote({
    source_kind: sourceKind, source_id: sourceId, task_type: taskType, target, budget: budget.budget(),
    deadline: deadline ? new Date(deadline).toISOString() : undefined, note: note || undefined,
  }), onDone, () => setNote(""));
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={taskType} onChange={(e) => setTaskType(e.target.value as TaskType)} aria-label="Task type">
        {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <ParticipantSelect value={target} onChange={setTarget} />
      <BudgetFields state={budget} />
      <Field label="Deadline"><input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></Field>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional, attributed)" aria-label="Note" className="pp-wide" />
      <button disabled={state.busy}>Promote</button>
      <Feedback error={state.error} done={state.done} label="Promoted to an assignment." />
    </form>
  );
}

export function CommissionForm({ subjectKind, subjectId, onDone, defaultTaskType = "writing", defaultNote = "", defaultTarget = "" }: {
  subjectKind?: string; subjectId?: string; onDone?: () => void; defaultTaskType?: TaskType; defaultNote?: string; defaultTarget?: string;
}) {
  const [taskType, setTaskType] = useState<TaskType>(defaultTaskType);
  const [target, setTarget] = useState(defaultTarget);
  const [note, setNote] = useState(defaultNote);
  const budget = useBudget();
  const state = useSubmit(() => commission({
    task_type: taskType, target, budget: budget.budget(), subject_kind: subjectKind, subject_id: subjectId, note,
  }), onDone, () => setNote(""));
  return (
    <form className="action-form" onSubmit={state.submit}>
      <select value={taskType} onChange={(e) => setTaskType(e.target.value as TaskType)} aria-label="Commission type">
        {COMMISSION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <ParticipantSelect value={target} onChange={setTarget} />
      <BudgetFields state={budget} />
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Scope of the commission" aria-label="Scope" required className="pp-wide" />
      <button disabled={state.busy}>Commission</button>
      <Feedback error={state.error} done={state.done} label="Commissioned." />
    </form>
  );
}

// Spec v3 V14: anyone may request a replication of an artifact; the budget defaults to the commons' own.
export function ReplicationRequestForm({ artifact, onDone }: { artifact: string; onDone?: () => void }) {
  const [target, setTarget] = useState("");
  const [minutes, setMinutes] = useState("");
  const state = useSubmit(() => requestReplication({
    artifact, target, ...(minutes ? { budget: { minutes: Number(minutes) } } : {}),
  }), onDone, () => setMinutes(""));
  return (
    <form className="action-form" onSubmit={state.submit}>
      <ParticipantSelect value={target} onChange={setTarget} />
      <Field label="Minutes (default: the commons')">
        <input type="number" min={1} step={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
      </Field>
      <button disabled={state.busy}>Request replication</button>
      <Feedback error={state.error} done={state.done} label="Replication commissioned." />
    </form>
  );
}

// A person's ask is a budgeted `question` request within their allowance; the agent receives it labelled as
// attributed board content from a human participant, not as an instruction.
export function AskForm({ target, parent, onDone }: { target: string; parent?: string; onDone?: () => void }) {
  const [body, setBody] = useState("");
  const [minutes, setMinutes] = useState("15");
  const state = useSubmit(() => ask({ target, body, parent, budget: { minutes: Number(minutes) } }), onDone, () => setBody(""));
  return (
    <form className="action-form" onSubmit={state.submit}>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} required aria-label="Question" placeholder="Question (a durable request; no chat)" />
      <Field label="Budget (minutes)">
        <input type="number" min={1} step={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} required />
      </Field>
      <button disabled={state.busy}>Ask</button>
      <Feedback error={state.error} done={state.done} label="Question queued." />
    </form>
  );
}

function size(bytes: number) {
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1048576).toFixed(1)} MiB`;
}

// Uploads become library objects with receipts: evidence of kind upload, never executed or rendered.
export function UploadButton({ onUploaded, label = "Attach file" }: { onUploaded: (upload: UploadRecord) => void; label?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const id = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const choose = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onUploaded(await uploadFile(file));
    } catch (reason) {
      setError(explain(reason));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };
  return (
    <span className="pp-upload">
      <input ref={input} id={id} type="file" className="pp-file" onChange={(e) => choose(e.target.files)} disabled={busy} />
      <label htmlFor={id} className="pp-file-label" aria-disabled={busy}>{busy ? "Uploading…" : label}</label>
      {error && <span className="error" role="alert">{error}</span>}
    </span>
  );
}

export function AttachedUploads({ uploads, onRemove }: { uploads: UploadRecord[]; onRemove?: (id: string) => void }) {
  if (!uploads.length) return null;
  return (
    <ul className="pp-attached" aria-label="Attached uploads">
      {uploads.map((u) => (
        <li key={u.id}>
          <span className="mono">{u.name}</span> <span className="muted">{u.media_type} · {size(u.size)} · sha256 {u.blob.slice(0, 12)}…</span>
          {onRemove && <button type="button" onClick={() => onRemove(u.id)} aria-label={`Remove ${u.name}`}>remove</button>}
        </li>
      ))}
    </ul>
  );
}

// New post or reply. Attached uploads travel as `upload_ids` and appear in the post's evidence.
export function PostForm({ parent, supersedes, onDone }: { parent?: string; supersedes?: string; onDone?: (id: string) => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const state = useSubmit(async () => {
    const made = await createPost({ title, body, parent, supersedes, upload_ids: uploads.map((u) => u.id) });
    onDone?.(made.id);
  }, undefined, () => (setTitle(""), setBody(""), setUploads([])));
  return (
    <form className="action-form" onSubmit={state.submit}>
      <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={300} aria-label="Title"
        placeholder={parent ? "Reply title" : "Title"} className="pp-wide" />
      <textarea value={body} onChange={(e) => setBody(e.target.value)} required rows={5} aria-label="Body"
        placeholder="Markdown. Posts are attributed evidence on the record, never instructions." />
      <AttachedUploads uploads={uploads} onRemove={(id) => setUploads((list) => list.filter((u) => u.id !== id))} />
      <UploadButton onUploaded={(u) => setUploads((list) => [...list.filter((x) => x.id !== u.id), u])} />
      <button disabled={state.busy}>{parent ? "Reply" : "Post"}</button>
      <Feedback error={state.error} done={state.done} label="Posted." />
    </form>
  );
}
