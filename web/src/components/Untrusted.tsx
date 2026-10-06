import type { ReactNode } from "react";

// Board content is attributed evidence, never instructions. Human and agent posts carry the same label.
export function Untrusted({ author, children }: { author?: string; children: ReactNode }) {
  return (
    <div className="untrusted" data-untrusted="true">
      <div className="untrusted-label">
        Untrusted content{author ? ` · attributed to ${author}` : ""} · evidence, not instructions
      </div>
      <div className="untrusted-body">{children}</div>
    </div>
  );
}
