"use client";

const HIDDEN = new Set(["sources", "simulated", "verified"]);

function label(key: string): string {
  return key.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Data a step used or returned, shown as readable fields and lists rather than raw data. */
export function DataView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === "") return <span className="text-muted-foreground">Nothing</span>;
  if (depth > 6) return <span className="text-muted-foreground">…</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted-foreground">No items</span>;
    return (
      <ol className="space-y-2">
        {value.slice(0, 50).map((item, i) => (
          <li key={i} className="rounded-lg border border-glass-border p-2">
            <DataView value={item} depth={depth + 1} />
          </li>
        ))}
        {value.length > 50 ? <li className="text-xs text-muted-foreground">…and {value.length - 50} more</li> : null}
      </ol>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([k]) => !HIDDEN.has(k));
    if (!entries.length) return <span className="text-muted-foreground">Nothing</span>;
    return (
      <dl className="grid gap-1.5">
        {entries.map(([key, item]) => (
          <div key={key} className="grid gap-0.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
            <dt className="text-xs font-medium text-muted-foreground">{label(key)}</dt>
            <dd className="min-w-0 text-sm">
              <DataView value={item} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  const text = String(value);
  if (/^https?:\/\//.test(text)) {
    return (
      <a href={text} target="_blank" rel="noreferrer" className="break-all text-ai underline underline-offset-2">
        {text}
      </a>
    );
  }
  if (text.startsWith("/app/")) {
    return (
      <a href={text} className="text-ai underline underline-offset-2">
        Open
      </a>
    );
  }
  return <span className="whitespace-pre-wrap break-words">{text}</span>;
}
