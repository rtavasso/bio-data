// Workbench writes (spec v2 V4) and membership writes (V9): thin wrappers over the attributed write API.
import { post } from "../../api";
import type { Anchor, Budget, RequestRow } from "../participation/writes";
import type { Membership, SavedView } from "../../types/workbench";

export const saveView = (body: { questions: string[]; participants: string[]; since?: string | null; until?: string | null }) =>
  post<SavedView>("/api/views", body);

export const markInboxRead = (body: { items?: string[]; all?: boolean }) =>
  post<{ participant: string; marked: string[]; read_at: string | null }>("/api/me/inbox/read", body);

// A reply in a comment thread at an anchor: the server copies the thread's recorded anchor onto the reply.
export const replyAtAnchor = (comment: string, body: string) =>
  post<{ post: string; parent: string; in_reply_to: string }>(`/api/comments/${encodeURIComponent(comment)}/replies`, { body });

// "Request review" on an anchored claim: a commission of task type review, the claim as subject, the anchor in the note.
export const requestReview = (body: {
  claim: string; target: string; budget: Budget; comment?: string; anchor?: Anchor; deadline?: string; note?: string;
}) => post<RequestRow & { claim: string; anchor: Anchor; anchor_comment: string | null }>("/api/reviews", body);

export const grantMember = (participant: string, reason: string) =>
  post<Membership>("/api/members", { participant, reason });

export const revokeMember = (participant: string, reason: string) =>
  post<Membership>(`/api/members/${encodeURIComponent(participant)}/revoke`, { reason });

// The share link of a view: the current screen with `?view=<hash>`.
export function shareLink(hash: string, location: { origin: string; pathname: string } = window.location): string {
  return `${location.origin}${location.pathname}?view=${hash}`;
}
