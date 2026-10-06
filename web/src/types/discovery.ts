// Discovery area (M1.8 search, M5.2 watchers): shapes returned by /api/search and /api/watchers.

export type SearchFamily = "forum" | "artifact" | "work" | "data" | "claim" | "resource";
export type SearchScope = "library" | "workspaces";

export interface SearchSource {
  scope: "library" | "workspace";
  participant?: string;
  name?: string;
  total?: number;
  error?: string;
  detail?: string;
  coverage?: { documents: number; with_current_vector: number; without_current_vector: number };
}

export interface SearchItem {
  id: string;
  family: SearchFamily | string;
  subject: string;
  record_id: string;
  title: string;
  summary: string;
  provider: string;
  format: string;
  level: number;
  score: number;
  rank: number;
  locator?: string;
  source: SearchSource;
  content_is_untrusted_data: boolean;
}

export interface SearchResult {
  query: string;
  vector: boolean;
  scope: SearchScope;
  family: string | null;
  method: string;
  model: string | null;
  total: number;
  offset: number;
  items: SearchItem[];
  next_offset: number | null;
  sources: SearchSource[];
  limitations: string[];
}

export interface WatcherQuery {
  query: string;
  filters: Record<string, string | number | boolean | null>;
  max_pages: number;
  page_size: number;
}

export interface WatcherRunSummary {
  id: string;
  created: string;
  found: number;
  post: string | null;
}

export interface Watcher {
  id: string;
  item: string;
  author: string;
  query: WatcherQuery;
  provider: string;
  interval_seconds: number;
  next_due: number;
  next_due_utc: string;
  enabled: boolean;
  created: string;
  runs: number;
  last_run: WatcherRunSummary | null;
}

export interface WatcherList {
  items: Watcher[];
  providers: string[];
  cadence: string;
}

export interface WatcherHit {
  accession: string;
  provider: string;
  title: string;
  pmcid?: string;
  doi?: string;
  pmid?: string;
}

export interface WatcherRun {
  id: string;
  watcher: string;
  item: string;
  provider: string;
  query: WatcherQuery;
  receipt_blob: string | null;
  found: WatcherHit[];
  post: string | null;
  created: string;
  receipt?: { new: WatcherHit[]; warnings: string[]; exhausted: boolean; pages: { response_blob: string | null; locator: string | null }[] };
}
