// Workbench (spec v2 V4) and access (V9) API shapes.
import type { NumberPointer } from "./board";

export type InboxKind = "answer" | "reply" | "correction" | "watcher_hit";

export interface InboxItem {
  id: string;
  kind: InboxKind;
  seq: number | null;
  created: string | null;
  post: string | null;
  title: string | null;
  author: string | null;
  hidden: boolean;
  reason: string | null;
  read: boolean;
  read_at: string | null;
  relation: Record<string, unknown>;
  request?: string;
  task_type?: string | null;
  asked?: string;
  in_reply_to?: string;
  to_comment?: boolean;
  anchored?: boolean;
  corrects?: string;
  marks?: { mark: string; target_kind: string; target_id: string }[];
  item?: string;
  watcher_run?: string;
  new?: number;
}

export interface Inbox {
  participant: string;
  items: InboxItem[];
  total: number;
  unread: number;
  latest: number;
  sequence: number;
}

export interface ViewSpec {
  format: 1;
  questions: string[];
  participants: string[];
  since: string | null;
  until: string | null;
}

export interface SavedView {
  view: string;
  spec: ViewSpec;
  created_by: string;
  created: string;
  existing?: boolean;
  participant_names?: Record<string, string | null>;
}

export interface ReadingPost {
  type: "post";
  id: string;
  seq: number;
  created: string;
  hidden?: boolean;
  reason?: string | null;
  post_kind?: string;
  author?: { id: string; name?: string; kind?: string };
  parent?: string | null;
  supersedes?: string | null;
  superseded_by?: string[];
  title?: string | null;
  body?: string | null;
  withheld?: { title?: string; placeholder?: string } | null;
  anchor?: { quote?: string | null } | null;
  in_reply_to?: string | null;
  evidence?: {
    artifacts: { id: string; title?: string | null; present?: boolean; output_role?: string }[];
    notebook?: { question?: string } | null;
    run?: string | null;
  };
  numbers?: NumberPointer[];
}

export interface ReadingClaim {
  type: "claim";
  id: string;
  post: string;
  created: string;
  seq: number;
  text: string;
  status: string;
  scope: Record<string, unknown>;
  pointers: { kind: string; id: string; locator?: string }[];
  withdrawn_by?: string | null;
  author: string;
}

export interface ReadingNumber extends Pick<NumberPointer, "text" | "status" | "scope" | "pointers"> {
  post: string;
  offset: number;
}

export interface Reading {
  root: string;
  focus: string;
  items: (ReadingPost | ReadingClaim)[];
  numbers: ReadingNumber[];
  counts: { posts: number; corrections: number; claims: number; numbers: number };
}

export interface AccessStanding {
  mode: string;
  read: "public" | "members" | "private" | "local";
  authenticated: boolean;
  participant: string | null;
  member: boolean;
  reason: string | null;
  note: string;
}

export interface AuditEvent {
  seq: number;
  kind: string;
  created: string;
  body: Record<string, unknown>;
  redacted?: string;
}

export interface AuditPage {
  items: AuditEvent[];
  total: number;
  facets: Record<string, number>;
  kinds: string[];
  next_before: number | null;
  login_failures_recorded: number | null;
}

export interface Membership {
  participant: string;
  name: string;
  kind: string;
  state: "member" | "revoked";
  actor: string;
  reason: string;
  updated: string;
}
