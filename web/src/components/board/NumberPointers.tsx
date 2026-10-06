import { Link } from "react-router-dom";
import type { NumberPointer } from "../../types/board";
import { Badge } from "./Badges";
import { short } from "./format";

const SCOPE = { line: "same line", post: "post evidence", none: "no pointer" } as const;

// Every number in the post with the artifact pointers the post itself carries. Numbers without a pointer
// are listed, not hidden: the reader decides what an unpointed number is worth.
export function NumberPointers({ numbers }: { numbers: NumberPointer[] }) {
  if (!numbers.length) return <p className="muted">No numbers in this post.</p>;
  const unpointed = numbers.filter((n) => n.scope === "none").length;
  return (
    <>
      {unpointed > 0 && <p className="error">{unpointed} number{unpointed > 1 ? "s have" : " has"} no artifact pointer.</p>}
      <table className="numbers">
        <thead>
          <tr><th scope="col">Number</th><th scope="col">Pointer</th><th scope="col">Artifacts</th></tr>
        </thead>
        <tbody>
          {numbers.map((n) => (
            <tr key={n.offset} className={n.scope === "none" ? "unpointed" : undefined}>
              <td className="mono">{n.text}</td>
              <td><Badge tone={n.scope === "none" ? "bad" : n.scope === "line" ? "good" : "plain"}>{SCOPE[n.scope]}</Badge></td>
              <td>
                {n.pointers.map((p) => (
                  <span key={p.artifact} className="pointer">
                    {p.location.store === "missing" ? (
                      <span className="error mono" title={p.artifact}>{short(p.artifact)} (not found)</span>
                    ) : (
                      <Link to={`/artifact/${p.artifact}`} className="mono" title={p.artifact}>{short(p.artifact)}</Link>
                    )}
                    {p.location.store === "workspace" && <span className="muted"> (unpublished, in a workspace)</span>}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
