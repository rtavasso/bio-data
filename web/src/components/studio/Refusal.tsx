import type { Problem } from "../../types/studio";

// A refused write-up: every unpointed number and unresolved pointer with its line and the source line, the
// offending span marked. The source is untrusted text and is shown as text.

const LABELS: Record<Problem["kind"], string> = {
  unpointed_number: "Number without a claim or artifact pointer",
  unresolved_pointer: "Pointer does not resolve",
  pointer_kind_not_allowed: "Not a citable record",
  figure_not_artifact: "Figure does not reference an artifact",
  post_hidden: "Hidden by moderation",
};

function Context({ problem, source }: { problem: Problem; source: string }) {
  const lineStart = source.lastIndexOf("\n", Math.max(0, problem.offset - 1)) + 1;
  const lineEnd = source.indexOf("\n", problem.offset + problem.length);
  const line = source.slice(lineStart, lineEnd < 0 ? source.length : lineEnd);
  const start = problem.offset - lineStart;
  if (start < 0 || start > line.length) return <code>{problem.context}</code>;
  return (
    <code className="st-context">
      {line.slice(0, start)}<mark>{line.slice(start, start + problem.length)}</mark>{line.slice(start + problem.length)}
    </code>
  );
}

export function Refusal({ problems, source }: { problems: Problem[]; source?: string | null }) {
  return (
    <section className="st-refusal" role="alert" aria-label="Renderer refusal">
      <h2>Not served: {problems.length} problem{problems.length === 1 ? "" : "s"}</h2>
      <p>
        Every number must sit inside a claim or artifact pointer, or in a sentence that cites one, and every pointer
        must resolve. Post pointers give context only. Fix the write-up (or commission a new one); nothing is rendered
        until then.
      </p>
      <ol className="st-problems">
        {problems.map((problem, n) => (
          <li key={n}>
            <span className="st-problem-kind">{LABELS[problem.kind] ?? problem.kind}</span>{" "}
            <strong className="mono">{problem.text ?? problem.pointer ?? ""}</strong>{" "}
            <span className="muted">line {problem.line}, offset {problem.offset}: {problem.reason}</span>
            {source ? <div><Context problem={problem} source={source} /></div> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
