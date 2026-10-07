import { Link } from "react-router-dom";
import type { NumberPointer, NumberRecordPointer, NumberStatus } from "../../types/board";
import { Badge } from "./Badges";
import { short } from "./format";

// The number checker's report for a post (spec v2 C5, C11, V2). Numbers with a pointer at the number are
// verified against the cited record (claim text or scope, the cited cell, key or line) or shown as unverified;
// numbers covered only by the post's evidence list are listed as "this post's evidence", not as links from the
// number; numbers without any pointer are listed as unpointed. Nothing is hidden.

export const STATUS_LABEL: Record<NumberStatus, string> = {
  verified: "verified", unverified: "unverified", post_scoped: "this post's evidence", unpointed: "no pointer",
};
const SCOPE_LABEL = { cell: "cell", claim: "claim", line: "artifact", post: "post", none: "none" } as const;

export function statusOf(n: NumberPointer): NumberStatus {
  if (n.status) return n.status;
  return n.scope === "none" ? "unpointed" : n.scope === "post" ? "post_scoped" : "unverified";
}

export function pointerRoute(p: NumberRecordPointer): string | null {
  if (p.route) return p.route;
  const id = p.artifact ?? p.id;
  if (!id) return null;
  if (id.startsWith("artifact_")) return `/artifact/${id}` + (p.locator ? `?locator=${encodeURIComponent(p.locator)}` : "");
  if (id.startsWith("claim_")) return null;
  if (id.startsWith("post_")) return `/post/${id}`;
  return null;
}

function Record({ p }: { p: NumberRecordPointer }) {
  const id = p.artifact ?? p.id ?? "";
  const route = pointerRoute(p);
  const missing = p.location?.store === "missing";
  return (
    <span className="pointer">
      {missing || !route ? (
        <span className={missing ? "error mono" : "mono"} title={id}>{short(id)}{missing ? " (not found)" : ""}</span>
      ) : (
        <Link to={route} className="mono" title={id}>{short(id)}</Link>
      )}
      {p.locator && <span className="mono muted"> #{p.locator}</span>}
      {p.location?.store === "workspace" && <span className="muted"> (unpublished, in a workspace)</span>}
    </span>
  );
}

export function NumberPointers({ numbers }: { numbers: NumberPointer[] }) {
  if (!numbers.length) return <p className="muted">No numbers in this post.</p>;
  const pointed = numbers.filter((n) => ["verified", "unverified"].includes(statusOf(n)));
  const postScoped = numbers.filter((n) => statusOf(n) === "post_scoped");
  const unpointed = numbers.filter((n) => statusOf(n) === "unpointed");
  const evidence = new Map<string, NumberRecordPointer>();
  for (const n of postScoped) for (const p of n.pointers) evidence.set(p.artifact ?? p.id ?? "", p);
  const verified = pointed.filter((n) => statusOf(n) === "verified").length;
  return (
    <div className="number-report">
      <p className="meta" aria-label="Number coverage">
        {numbers.length} number{numbers.length === 1 ? "" : "s"}: {verified} verified · {pointed.length - verified} unverified ·{" "}
        {postScoped.length} covered only by this post's evidence · {unpointed.length} unpointed
      </p>
      {pointed.length > 0 && (
        <table className="numbers" aria-label="Numbers pointed at a record">
          <thead>
            <tr><th scope="col">Number</th><th scope="col">Check</th><th scope="col">Record</th><th scope="col">Why</th></tr>
          </thead>
          <tbody>
            {pointed.map((n) => {
              const status = statusOf(n);
              return (
                <tr key={n.offset} className={`num-row num-row-${status}`}>
                  <td className="mono">{n.text}</td>
                  <td><Badge tone={status === "verified" ? "good" : "warn"}>{STATUS_LABEL[status]}</Badge> <span className="muted small">{SCOPE_LABEL[n.scope]}</span></td>
                  <td>{n.pointers.map((p, i) => <Record key={i} p={p} />)}</td>
                  <td className="muted small">
                    {n.pointers.map((p) => p.result === "verified" ? `found at ${p.at ?? "record"}` : p.reason).filter(Boolean).join("; ")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {postScoped.length > 0 && (
        <section aria-label="This post's evidence">
          <h3>This post's evidence (not pointed at the number)</h3>
          <p className="muted small">
            These numbers have no pointer of their own; the post names evidence as a whole. Open it to check them:
          </p>
          <p className="mono">{postScoped.map((n) => n.text).join(" · ")}</p>
          <p>{Array.from(evidence.values()).map((p, i) => <Record key={i} p={p} />)}</p>
        </section>
      )}
      {unpointed.length > 0 && (
        <section aria-label="Unpointed numbers">
          <p className="error">{unpointed.length} number{unpointed.length > 1 ? "s have" : " has"} no pointer.</p>
          <p className="mono">{unpointed.map((n) => n.text).join(" · ")}</p>
        </section>
      )}
    </div>
  );
}
