import { post, send, uploadBytes, type Participant } from "../../api";
import { withBase } from "../../base";
import type {
  BudgetSummary, Credential, IssuedToken, MarkRecord, ModerationRecord, Pointer, UploadRecord,
} from "../../types/participation";

// Thin wrappers over the attributed write API (M8.2). The server checks permissions,
// attaches the caller's identity and calls the same board functions agents use.

export type TargetKind = "post" | "question" | "artifact" | "node" | "claim" | "run";
export type MarkKind = "checked_source" | "reproduced" | "disputed";
export type TaskType = "research" | "review" | "replication" | "scouting" | "writing" | "digest";
export const TASK_TYPES: TaskType[] = ["research", "review", "replication", "scouting", "writing", "digest"];
export const COMMISSION_TYPES: TaskType[] = ["review", "replication", "writing", "digest"];
export const MARK_KINDS: MarkKind[] = ["checked_source", "reproduced", "disputed"];

export interface Anchor {
  kind: "paragraph" | "line" | "row" | "node";
  blob?: string;
  offset?: number;
  length?: number;
  row_key?: string;
  node_id?: string;
  quote?: string;
}

export interface Budget {
  minutes?: number;
  tokens?: number;
  download_bytes?: number;
}

export interface RequestRow {
  id: string;
  post: string;
  target: string;
  state: string;
  task_type?: string | null;
}

// Asking the author makes a typed `question` request with a budget (default 15 minutes) within the person's allowance.
export const comment = (body: {
  target_kind: TargetKind; target_id: string; anchor?: Anchor; body: string; ask_author: boolean; budget?: Budget;
}) => post<{ post: string; anchor: Anchor | null; request?: RequestRow | null }>("/api/comments", body);

export const mark = (body: { target_kind: "post" | "claim" | "artifact"; target_id: string; kind: MarkKind; note: string; pointers: Pointer[] }) =>
  post<MarkRecord>("/api/marks", body);

export const promote = (body: {
  source_kind: "frontier_item" | "post" | "claim" | "shared_experiment"; source_id: string; task_type: TaskType; target: string;
  budget: Budget; deadline?: string; note?: string;
}) => post<RequestRow>("/api/promotions", body);

export const commission = (body: {
  task_type: TaskType; target: string; budget: Budget; deadline?: string; subject_kind?: string; subject_id?: string; note: string;
}) => post<RequestRow>("/api/commissions", body);

// A person's ask: a typed `question` request with a budget, delivered as attributed human content (never an instruction).
export const ask = (body: { target: string; body: string; parent?: string; budget?: Budget }) =>
  post<RequestRow>("/api/requests", body);

export const createPost = (body: { title: string; body: string; parent?: string; supersedes?: string; upload_ids?: string[] }) =>
  post<{ id: string }>("/api/posts", body);

export const uploadFile = (file: File) => uploadBytes<UploadRecord>("/api/uploads", file);

export const uploadContentUrl = (id: string) => withBase(`/api/uploads/${encodeURIComponent(id)}/content`);

// Accounts (M7).
export const login = (token: string) => post<Participant>("/api/session", { token });
export const logout = () => send<{ logged_out: boolean }>("DELETE", "/api/session");
// The displayed role is the participant kind; profiles carry no self-asserted role.
export const updateProfile = (profile: { display_name?: string; affiliation?: string; orcid?: string }) =>
  send<Participant>("PATCH", "/api/me", profile);
export const createToken = (body: { participant?: string; label: string }) => post<IssuedToken>("/api/tokens", body);
export const revokeToken = (id: string) => send<Credential>("DELETE", `/api/tokens/${encodeURIComponent(id)}`);
export const createParticipant = (body: { name: string; kind: "human" | "operator" | "system"; display_name?: string; affiliation?: string; orcid?: string }) =>
  post<Participant>("/api/participants", body);
export const setAllowance = (participant: string, budget: Budget) =>
  send<BudgetSummary>("PUT", `/api/participants/${encodeURIComponent(participant)}/allowance`, budget);

// Moderation (M2.8), operator only.
export const moderatePost = (action: "hide" | "unhide", body: { post: string; reason: string }) =>
  post<ModerationRecord>(`/api/moderation/${action}`, body);
export const moderateParticipant = (action: "suspend" | "reinstate", body: { participant: string; reason: string }) =>
  post<ModerationRecord>(`/api/moderation/${action}`, body);

// Server refusals people can act on, in words.
const EXPLAIN: Record<string, string> = {
  authentication_required: "Log in first.",
  participant_suspended: "Your account is suspended: you can read but not write.",
  rate_limited: "Rate limit reached for this hour.",
  over_budget: "This exceeds your remaining budget allowance.",
  budget_required: "State a budget for every resource your allowance limits.",
  allowance_not_configured: "No allowance is configured for you: an operator sets the commons default ([allowance] in commons.toml) or yours.",
  permission_denied: "You do not have permission for this action.",
  anchor_quote_mismatch: "The selected text no longer matches the stored bytes.",
  upload_too_large: "The file is larger than the upload limit.",
};

export function explain(error: unknown): string {
  const reason = (error as { reason?: string })?.reason;
  const message = (error as Error)?.message ?? String(error);
  return reason && EXPLAIN[reason] ? `${EXPLAIN[reason]} (${message})` : message;
}
