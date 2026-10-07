import type { Problem } from "../../types/studio";

// A refused write-up (spec v2 C5): the checker's recorded verdict, every problem with its line and the source line
// (the location evidence), the offending span marked. The write-up itself is withheld on every surface; the
// source lines are untrusted text and are shown as text.

const LABELS: Record<Problem["kind"], string> = {
  unpointed_number: "Number without a claim or artifact pointer at it",
  unresolved_pointer: "Pointer does not resolve",
  pointer_kind_not_allowed: "Not a citable record",
  figure_not_artifact: "Figure does not reference an artifact",
  post_hidden: "Hidden by moderation",
  claimless_post_cited: "Cites a post without ledger claims",
  invalid_locator: "Locator does not parse",
};

function Context({ problem, source }: { problem: Problem; source?: string | null }) {
  // The served verdict carries the source line and its start offset; older responses carried the whole source.
  let line = problem.context ?? "";
  let lineStart = problem.context_start ?? -1;
  if (source) {
    lineStart = source.lastIndexOf("\n", Math.max(0, problem.offset - 1)) + 1;
    const lineEnd = source.indexOf("\n", problem.offset + problem.length);
    line = source.slice(lineStart, lineEnd < 0 ? source.length : lineEnd);
  }
  const start = problem.offset - lineStart;
  if (lineStart < 0 || start < 0 || start > line.length) return problem.context ? <code>{problem.context}</code> : null;
  return (
    <code className="st-context">
      {line.slice(0, start)}<mark>{line.slice(start, start + problem.length)}</mark>{line.slice(start + problem.length)}
    </code>
  );
}

export function Refusal({ problems, source, placeholder }: { problems: Problem[]; source?: string | null; placeholder?: string }) {
  return (
    <section className="st-refusal" role="alert" aria-label="Renderer refusal">
      <h2>Not served: {problems.length} problem{problems.length === 1 ? "" : "s"}</h2>
      <p>
        {placeholder ?? "This write-up is withheld."} Every number needs its own claim or artifact pointer (a pointer
        covers the numbers in its link text, or the one number right before its bracket in the same clause), every
        pointer must resolve, and a writing task cites only posts with ledger claims.
      </p>
      <ol className="st-problems">
        {problems.map((problem, n) => (
          <li key={n}>
            <span className="st-problem-kind">{LABELS[problem.kind] ?? problem.kind}</span>{" "}
            <strong className="mono">{problem.text ?? problem.pointer ?? ""}</strong>{" "}
            <span className="muted">line {problem.line}, offset {problem.offset}: {problem.reason}</span>
            {(source || problem.context) ? <div><Context problem={problem} source={source} /></div> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
