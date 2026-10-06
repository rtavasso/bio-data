// Display helpers for record identifiers, times and sizes. Identifiers stay complete in links and titles.

export function short(id: string | null | undefined, keep = 12): string {
  if (!id) return "";
  const cut = id.indexOf("_");
  const prefix = cut > 0 ? id.slice(0, cut + 1) : "";
  const rest = id.slice(prefix.length);
  return rest.length > keep ? `${prefix}${rest.slice(0, keep)}…` : id;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function size(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "size unknown";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "–";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}
