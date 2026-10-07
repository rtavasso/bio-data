import { Link } from "react-router-dom";
import type { NumberPointer, NumberRecordPointer, NumberStatus } from "../../types/board";
import { Badge } from "./Badges";
import { short } from "./format";

// The number checker's report for a post (spec v2 C5, C11, V2). Numbers with a pointer at the number are
// verified against the cited record (claim text or scope, the cited cell, key or line) or shown as unverified;
// numbers covered only by the post's evidence list are listed as "this post's evidence", not as links from the
// number; numbers without any pointer are listed as unpointed. Nothing is hidden. Spec v3: a pointer at a whole
// artifact (no locator) has its own "text match" badge and verifies only when the value occurs once (B6); a
// person's curated pointer is badged "curated", names the curator and is never shown as the author's (G2).

export const STATUS_LABEL: Record<NumberStatus, string> = {
  verified: "verified", unverified: "unverified", post_scoped: "this post's evidence", unpointed: "no pointer",
};
const SCOPE_LABEL = { cell: "cell", claim: "claim", line: "line", text: "text match", curated: "curated", post: "post",
  none: "none" } as const;

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
      {p.curated && <span className="muted"> · curated by {p.curator_name ?? p.curator}{p.note ? `: ${p.note}` : ""}</span>}
    </span>
  );
}

// The badge of a pointed number: verified author pointers are good; a text match (B6) and a curated pointer (G2)
// carry their own badge, so neither reads as the author's verified cell, claim or line.
function CheckBadge({ n }: { n: NumberPointer }) {
  const status = statusOf(n);
  if (n.scope === "curated") {
    return <Badge tone={status === "verified" ? "accent" : "warn"}>{status === "verified" ? "curated" : "curated, unverified"}</Badge>;
  }
  if (n.scope === "text") {
    return <Badge tone={status === "verified" ? "plain" : "warn"}>{status === "verified" ? "text match" : "unverified"}</Badge>;
  }
  return <Badge tone={status === "verified" ? "good" : "warn"}>{STATUS_LABEL[status]}</Badge>;
}

export function NumberPointers({ numbers }: { numbers: NumberPointer[] }) {
  if (!numbers.length) return <p className="muted">No numbers in this post.</p>;
  const pointed = numbers.filter((n) => ["verified", "unverified"].includes(statusOf(n)));
  const postScoped = numbers.filter((n) => statusOf(n) === "post_scoped");
  const unpointed = numbers.filter((n) => statusOf(n) === "unpointed");
  const evidence = new Map<string, NumberRecordPointer>();
  for (const n of postScoped) for (const p of n.pointers) evidence.set(p.artifact ?? p.id ?? "", p);
  const verified = pointed.filter((n) => statusOf(n) === "verified" && !["text", "curated"].includes(n.scope)).length;
  const textMatches = pointed.filter((n) => statusOf(n) === "verified" && n.scope === "text").length;
  const curated = pointed.filter((n) => n.scope === "curated").length;
  const unlocatable = numbers.filter((n) => n.unlocatable);
  return (
    <div className="number-report">
      <p className="meta" aria-label="Number coverage">
        {numbers.length} number{numbers.length === 1 ? "" : "s"}: {verified} verified · {textMatches > 0 && <>{textMatches} text match{textMatches === 1 ? "" : "es"} · </>}
        {curated > 0 && <>{curated} curated by a person · </>}{pointed.length - verified - textMatches - curated} unverified ·{" "}
        {postScoped.length} covered only by this post's evidence · {unpointed.length} unpointed
        {unlocatable.length > 0 && <> · {unlocatable.length} marked unlocatable</>}
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
                  <td><CheckBadge n={n} /> <span className="muted small">{SCOPE_LABEL[n.scope]}</span></td>
                  <td>{[...n.pointers, ...(n.curated_pointers ?? [])].map((p, i) => <Record key={i} p={p} />)}</td>
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
      {unlocatable.length > 0 && (
        <section aria-label="Marked unlocatable">
          <h3>Marked unlocatable by a person</h3>
          <ul>
            {unlocatable.map((n) => (
              <li key={n.offset}><span className="mono">{n.text}</span> <span className="muted small">— {n.unlocatable!.curator_name}: {n.unlocatable!.note}</span></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
