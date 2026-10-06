// Typed client for the commons HTTP API (M8). Every read is reproducible from the archive;
// every write is attributed to the caller and goes through board functions server-side.

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

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } }));
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
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
  content_policy: string;
}
