import { ApiError, post, send } from "../../api";
import type { Budget, RequestRow } from "../participation/actions";
import type { DigestSchedule, ExportResult, ReviewVerdict, Writeup } from "../../types/studio";
import type { MarkRecord } from "../../types/participation";

// Studio write calls (attributed; permissions checked server-side) and the write-up read, which must keep the
// 422 body: a refused write-up is a list of locations to show, not an error to swallow.

export async function loadWriteup(postId: string): Promise<Writeup> {
  const response = await fetch(`/api/studio/writeups/${encodeURIComponent(postId)}`, {
    credentials: "same-origin", headers: { Accept: "application/json" },
  });
  const body = await response.json().catch(() => null);
  if (response.ok || (response.status === 422 && body?.status === "refused")) return body as Writeup;
  throw new ApiError(response.status, body?.error ?? "request_failed", body?.detail ?? response.statusText);
}

export const submitReview = (body: {
  target_kind: "post" | "claim" | "artifact"; target_id: string; verdicts: ReviewVerdict[]; summary?: string;
}) => post<{ post: string; marks: MarkRecord[]; skipped: { criterion?: string; reason: string }[] }>("/api/studio/reviews", body);

export const createExport = (body: { scope: "board" | "thread" | "question"; id?: string }) =>
  post<ExportResult>("/api/exports", body);

export interface DigestScope {
  query?: string;
  questions?: string[];
  posts?: string[];
}

export const scheduleDigest = (body: { target: string; scope: DigestScope; cadence: "daily" | "weekly" | number; budget: Budget }) =>
  post<DigestSchedule>("/api/studio/digests", body);

export const commissionDigest = (body: { target: string; scope: DigestScope; budget: Budget; since?: string; until?: string; note?: string }) =>
  post<RequestRow>("/api/studio/digests/commission", body);

export const cancelDigest = (id: string) => send<DigestSchedule>("DELETE", `/api/studio/digests/${encodeURIComponent(id)}`);

