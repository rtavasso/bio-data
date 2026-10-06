import { Link } from "react-router-dom";
import { withBase } from "../../base";
import { Untrusted } from "../Untrusted";
import type { Output } from "../../types/observatory-map";

// Artifacts linked to the question with their recorded relationships. Figures are shown from immutable
// blob bytes (served as images only when name and bytes agree; never HTML).

function Relationship({ output }: { output: Output }) {
  return (
    <>
      {output.relationships.map((r) => (
        <span key={r.relationship} className={`obs-chip${r.backed === false ? " warn" : r.backed ? " good" : ""}`}
          title={r.reason ?? undefined}>
          {r.relationship}{r.backed === false ? " · unbacked" : r.backed ? " · backed" : ""}
        </span>
      ))}
    </>
  );
}

export default function Outputs({ outputs }: { outputs: Output[] }) {
  if (!outputs.length) return <p className="muted">No artifacts are linked to this question.</p>;
  const figures = outputs.filter((o) => o.figure && o.blob_url);
  return (
    <>
      {figures.length > 0 && (
        <div className="q-figures">
          {figures.map((o) => (
            <figure key={o.artifact}>
              <Untrusted>
                <img src={withBase(o.blob_url!)} alt={o.title ?? o.output_name} loading="lazy" />
              </Untrusted>
              <figcaption>
                <Link to={`/artifact/${o.artifact}`}>{o.title ?? o.output_name}</Link> <span className="muted">{o.output_role}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      <div className="table-scroll">
        <table className="obs-table">
          <thead><tr><th>Artifact</th><th>Role</th><th>File</th><th>Relationship</th></tr></thead>
          <tbody>
            {outputs.map((o) => (
              <tr key={o.artifact}>
                <td>
                  <Link to={`/artifact/${o.artifact}`}>{o.title ?? o.artifact.slice(0, 24) + "…"}</Link>
                  {!o.present && <span className="obs-chip warn">missing from this workspace</span>}
                </td>
                <td className="mono">{o.output_role || "—"}</td>
                <td>
                  {o.blob_url ? <a href={withBase(o.blob_url)} target="_blank" rel="noopener noreferrer">{o.output_name || "bytes"}</a> : "—"}
                  {o.bytes !== null && o.bytes !== undefined && <span className="muted"> {o.bytes} B</span>}
                </td>
                <td><Relationship output={o} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
