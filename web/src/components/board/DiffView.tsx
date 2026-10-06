import { Link } from "react-router-dom";
import type { Diff } from "../../types/board";
import { Untrusted } from "../Untrusted";
import { short } from "./format";

// Line diff between a post and its superseder, with the numbers that changed listed first.
export function DiffView({ diff }: { diff: Diff }) {
  const { removed, added } = diff.numbers;
  return (
    <div className="diff">
      <p className="meta">
        From <Link to={`/post/${diff.from}`}>{short(diff.from)}</Link> to <Link to={`/post/${diff.to}`}>{short(diff.to)}</Link>
      </p>
      <p className="diff-numbers">
        Numbers removed: {removed.length ? removed.map((n, i) => <del key={i}>{n}</del>) : <span className="muted">none</span>}
        {" · "}
        added: {added.length ? added.map((n, i) => <ins key={i}>{n}</ins>) : <span className="muted">none</span>}
      </p>
      <Untrusted>
        <pre className="diff-lines" aria-label="Line diff">
          {diff.lines.map((line, i) => (
            <div key={i} className={`diff-${line.op === "+" ? "add" : line.op === "-" ? "del" : "same"}`}>
              <span aria-hidden="true">{line.op === "=" ? " " : line.op} </span>
              {line.text}
            </div>
          ))}
        </pre>
      </Untrusted>
    </div>
  );
}
