import { useState } from "react";
import { query } from "../../api";
import { useApi } from "../../useApi";
import { Status } from "../Status";
import { Untrusted } from "../Untrusted";
import type { Messages as MessagePage } from "../../types/observatory-map";

// Model-facing message bodies from the run's agent-state snapshot, bounded by the delivery's clock.
// Loaded on request and paginated; bodies are untrusted text, shown verbatim (never rendered as HTML).

const PAGE = 20;

export default function Messages({ path, agent }: { path: string; agent: string }) {
  const [offset, setOffset] = useState<number | null>(null);
  const page = useApi<MessagePage>(offset === null ? null : `${path}${query({ offset, limit: PAGE })}`);
  if (offset === null) {
    return <button type="button" onClick={() => setOffset(0)}>Load model-facing messages</button>;
  }
  const data = page.data;
  return (
    <div className="run-messages">
      <Status state={page} />
      {data && (
        <>
          <p className="muted">
            Messages {data.total ? data.offset + 1 : 0}–{data.offset + data.items.length} of {data.total}{" "}
            <button type="button" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - PAGE))}>Previous</button>{" "}
            <button type="button" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(data.offset + PAGE)}>Next</button>
          </p>
          {data.items.map((m) => (
            <Untrusted key={m.index} author={agent}>
              <p className="muted run-message-meta">
                #{m.index + 1}{m.role ? ` · ${m.role}` : ""}{m.timestamp ? ` · ${new Date(m.timestamp * 1000).toISOString()}` : ""}
              </p>
              <pre className="run-message">{m.content}</pre>
            </Untrusted>
          ))}
        </>
      )}
    </div>
  );
}
