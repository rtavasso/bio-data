// Typed client for the commons HTTP API (M8). Every read is reproducible from the archive;
// every write is attributed to the caller and goes through board functions server-side. Paths are
// root-relative ("/api/..."); they are resolved under the commons base path (see base.ts).
import { withBase } from "./base";
import { withView } from "./savedView";

export class ApiError extends Error {
  constructor(public status: number, public reason: string, public detail: string) {
    super(detail ? `${reason}: ${detail}` : reason);
  }
}

async function handle<T>(response: Response): Promise<T> {
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, body?.error ?? "request_failed", body?.detail ?? response.statusText);
  }
  return body as T;
}

export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// Reads carry the active saved view (`?view=` of the page, see savedView.ts): list endpoints and the map apply it.
export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(withBase(withView(path)), { credentials: "same-origin", headers: { Accept: "application/json" } }));
}

// Every write carries this header. A cross-origin page cannot add it without a CORS preflight the server
// never grants, so a person's session cookie (or a loopback server in local mode) cannot be used to forge writes.
export const WRITE_HEADER = { "X-Colloquy-Request": "1" } as const;

export async function send<T>(method: "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(withBase(path), {
      method,
      credentials: "same-origin",
      headers: { ...WRITE_HEADER, Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return send<T>("POST", path, body);
}

// Raw-body upload: the file name travels percent-encoded in X-Filename, the declared type in Content-Type.
export async function uploadBytes<T>(path: string, file: File): Promise<T> {
  return handle<T>(
    await fetch(withBase(path), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        ...WRITE_HEADER,
        Accept: "application/json",
        "Content-Type": file.type || "application/octet-stream",
        "X-Filename": encodeURIComponent(file.name),
      },
      body: file,
    }),
  );
}

export interface Participant {
  id: string;
  name: string;
  kind: "agent" | "human" | "operator" | "system";
  parent?: string | null;
  created: string;
  harness?: string;
  model?: string | null;
  effort?: string | null;
  started?: boolean;
  profile?: Record<string, string>;
}

export interface Health {
  ok: boolean;
  board_version: number;
  sequence: number;
  mode: string;
  demo: boolean;
  public_demo?: { fixture: string; board_sequence: number; real_data: boolean; tour?: { name: string } | null;
    first_screen?: string } | null;
  // Spec v3 V15: a public commons may let visitors sign in with a display name to comment and mark.
  visitor_signin?: boolean;
  read_policy?: string;
  content_policy: string;
}
