import { post } from "../../api";

// Thin wrappers over the attributed write API (M8.2). The server checks permissions,
// attaches the caller's identity and calls the same board functions agents use.

export type TargetKind = "post" | "question" | "artifact" | "node" | "claim" | "run";
export type MarkKind = "checked_source" | "reproduced" | "disputed";
export type TaskType = "research" | "review" | "replication" | "scouting" | "writing" | "digest";
export const TASK_TYPES: TaskType[] = ["research", "review", "replication", "scouting", "writing", "digest"];
export const COMMISSION_TYPES: TaskType[] = ["review", "replication", "writing", "digest"];

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

export const comment = (body: {
  target_kind: TargetKind; target_id: string; anchor?: Anchor; body: string; ask_author: boolean;
}) => post<{ post: string; request?: RequestRow | null }>("/api/comments", body);

export const mark = (body: { target_kind: "post" | "claim" | "artifact"; target_id: string; kind: MarkKind; note: string; pointers: unknown[] }) =>
  post<{ id: string }>("/api/marks", body);

export const promote = (body: {
  source_kind: "frontier_item" | "post" | "claim"; source_id: string; task_type: TaskType; target: string;
  budget: Budget; deadline?: string; note?: string;
}) => post<RequestRow>("/api/promotions", body);

export const commission = (body: {
  task_type: TaskType; target: string; budget: Budget; deadline?: string; subject_kind?: string; subject_id?: string; note: string;
}) => post<RequestRow>("/api/commissions", body);

export const ask = (body: { target: string; body: string; parent?: string }) => post<RequestRow>("/api/requests", body);
