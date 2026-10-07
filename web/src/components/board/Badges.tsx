import type { ReactNode } from "react";
import type { Mark, ReuseLink } from "../../types/board";
import { Untrusted } from "../Untrusted";
import { ParticipantLink } from "./People";
import { when } from "./format";

type Tone = "plain" | "good" | "warn" | "bad" | "accent";

export function Badge({ tone = "plain", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function KindBadge({ kind }: { kind: string | null | undefined }) {
  if (!kind) return null;
  const tone: Tone = kind === "answer" ? "accent" : kind === "question" ? "warn" : "plain";
  return <Badge tone={tone}>{kind.replace(/_/g, " ")}</Badge>;
}

// A hidden post is its identity and the moderation reason for every reader (spec v2 C2); bytes are never deleted.
export function HiddenNotice({ reason, revealed = false }: { reason?: string | null; revealed?: boolean }) {
  return (
    <p className="hidden-notice" role="note">
      Hidden by moderation: {reason ?? "no reason recorded"}.{" "}
      {revealed ? "Shown to you as an operator; other readers see only this notice."
        : "The record is preserved; operators can read it."}
    </p>
  );
}

export function ReuseBadge({ link }: { link: ReuseLink }) {
  if (link.relationship !== "reused") return <Badge>{link.relationship}</Badge>;
  const why = link.reason ?? (link.input_to?.length ? `input to ${link.input_to.join(", ")}` : undefined);
  return link.backed ? (
    <Badge tone="good" title={why}>reused · backed</Badge>
  ) : (
    <Badge tone="warn" title="no reuse reason and never a registration input">reused · unbacked</Badge>
  );
}

const MARK_TONE: Record<string, Tone> = { checked_source: "good", reproduced: "good", disputed: "bad" };

// Marks are attribution shown next to their target; they never change a status the platform computes.
export function MarkList({ marks }: { marks: Mark[] }) {
  if (!marks.length) return null;
  return (
    <Untrusted>
      <ul className="marks" aria-label="Verification marks">
        {marks.map((m) => (
          <li key={m.id}>
            <Badge tone={MARK_TONE[m.kind] ?? "plain"}>{m.kind.replace(/_/g, " ")}</Badge>{" "}
            <ParticipantLink id={m.participant} /> <span className="muted">{when(m.created)}</span>
            {m.note && <span className="mark-note"> — {m.note}</span>}
          </li>
        ))}
      </ul>
    </Untrusted>
  );
}
