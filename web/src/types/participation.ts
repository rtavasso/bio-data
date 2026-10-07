// Shapes returned by the participation and accounts API (daw.commons.participation, accounts, moderation).
import type { Participant } from "../api";
import type { Anchor, Budget, MarkKind, RequestRow } from "../components/participation/writes";

export interface Pointer {
  kind: string;
  id: string;
  locator?: string;
}

export interface MarkRecord {
  id: string;
  participant: string;
  participant_name?: string;
  participant_kind?: string;
  target_kind: "post" | "claim" | "artifact";
  target_id: string;
  kind: MarkKind;
  note: string;
  pointers: Pointer[];
  body_blob: string;
  created: string;
  attribution_not_status: true;
}

export interface UploadRecord {
  id: string;
  blob: string;
  name: string;
  uploader: string;
  media_type: string;
  size: number;
  receipt_blob: string;
  created: string;
}

export interface Credential {
  id: string;
  participant: string;
  label: string;
  created: string;
  revoked: string | null;
}

export interface IssuedToken {
  credential: Credential;
  token: string;
  note: string;
}

export interface BudgetSummary {
  allowance: Budget | null;
  spent: Required<Budget>;
  remaining: Budget | null;
  unlimited: boolean;       // operators: not budget-limited
  configured?: boolean;     // false: a person without an allowance; budgeted requests are refused (B13)
  setting?: string;         // where an operator configures the commons default
}

export interface StoredAnchor extends Anchor {
  target_kind: string;
  target_id: string;
  line?: number;
  row?: number;
}

export interface CommentSummary {
  id: string;
  created: string;
  parent: string | null;
  body: string;
  target: { kind: string; id: string; author: string | null } | null;
  anchor: StoredAnchor | null;
  request: { id: string; state: string; target: string; answer: string | null } | null;
}

export interface TaskRequest extends Omit<RequestRow, "task_type"> {
  task_type: string;
  budget: Budget | null;
  deadline: string | null;
  answer: string | null;
  created: string;
  updated: string;
  kind: "promotion" | "commission";
}

export interface MeSummary extends Participant {
  mode: "local" | "accounts";
  auth: "local" | "cookie" | "bearer";
  permissions: string[];
  writes_over_http: boolean;
  suspended: boolean;
  budget: BudgetSummary;
  /** A hidden post is `{id, hidden: true, reason}` here too (spec v2 C2). */
  posts: { id: string; created?: string; title?: string; kind?: string; parent?: string | null; hidden?: boolean;
    reason?: string | null }[];
  comments: CommentSummary[];
  promotions: TaskRequest[];
  commissions: TaskRequest[];
  marks: MarkRecord[];
  uploads: UploadRecord[];
  /** Snapshots this participant imported into the federation index (spec v3 B9); absent on older servers. */
  imports?: SnapshotImport[];
  inbox: RequestRow[];
  tokens: Credential[];
  csrf_header: string;
}

export interface SnapshotImport {
  snapshot: string;
  already_imported: boolean;
  scope?: Record<string, unknown> | null;
  counts?: Record<string, number> | null;
  index?: { claims: number; artifacts: number; citations: number; changed: boolean } | null;
  seq: number;
  created: string;
}

export interface ModerationRecord {
  target_kind: "post" | "participant";
  target_id: string;
  state: "hidden" | "visible" | "suspended" | "active";
  actor: string;
  reason: string;
  event_seq: number;
  updated: string;
}
