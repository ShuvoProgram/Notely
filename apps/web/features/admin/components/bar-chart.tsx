"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface Series<K extends string> {
  key: K;
  label: string;
  /** A CSS colour token, e.g. "var(--ai)". Status series use the reserved status tokens. */
  color: string;
}

/**
 * Daily bar chart built from plain elements (the app ships no chart library).
 *
 * Marks follow the dataviz spec: thin bars with 4px rounded data-ends on the baseline, a 2px
 * surface gap between stacked segments, one recessive grid, text in ink tokens (never the series
 * colour), a legend whenever there are two series, a hover/keyboard tooltip, and a table for
 * screen readers. One axis only.
 */
export function BarChart<K extends string>({
  data,
  series,
  label,
  height = 160,
  format = (v: number) => v.toLocaleString(),
}: {
  data: ({ date: string } & Record<K, number>)[];
  series: Series<K>[];
  label: string;
  height?: number;
  format?: (v: number) => string;
}) {
  const [active, setActive] = React.useState<number | null>(null);
  const totals = data.map((d) => series.reduce((sum, s) => sum + (d[s.key] || 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const dense = data.length > 45;
  const tickIdx = data.length ? [0, Math.floor((data.length - 1) / 2), data.length - 1] : [];
  const shown = active ?? null;

  return (
    <figure className="min-w-0">
      {series.length > 1 ? (
        <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex gap-2">
        {/* y axis: 0, mid, max */}
        <div className="flex w-8 shrink-0 flex-col justify-between text-right text-[10px] tabular-nums text-muted-foreground" style={{ height }} aria-hidden>
          <span className="-translate-y-1/2">{format(max)}</span>
          <span>{format(max / 2)}</span>
          <span className="translate-y-1/2">0</span>
        </div>
        <div
          className="relative min-w-0 flex-1 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          style={{ height }}
          tabIndex={0}
          role="img"
          aria-label={`${label}. Use left and right arrow keys to read each day.`}
          onMouseLeave={() => setActive(null)}
          onBlur={() => setActive(null)}
          onKeyDown={(e) => {
            if (!data.length) return;
            if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
              e.preventDefault();
              setActive((i) => {
                const cur = i ?? (e.key === "ArrowRight" ? -1 : data.length);
                return Math.min(data.length - 1, Math.max(0, cur + (e.key === "ArrowRight" ? 1 : -1)));
              });
            } else if (e.key === "Escape") setActive(null);
          }}
        >
          {/* recessive grid */}
          {[0, 0.5, 1].map((f) => (
            <div key={f} className="pointer-events-none absolute inset-x-0 border-t border-glass-border" style={{ top: `${f * 100}%` }} aria-hidden />
          ))}
          <div className={cn("absolute inset-0 flex items-end", dense ? "gap-px" : "gap-[3px]")}>
            {data.map((d, i) => {
              const total = totals[i] ?? 0;
              return (
                <div
                  key={d.date}
                  className="relative flex h-full min-w-0 flex-1 flex-col justify-end"
                  onMouseEnter={() => setActive(i)}
                  aria-hidden
                >
                  {/* hit target: the full column, not just the bar */}
                  <div className={cn("absolute inset-0 rounded-sm transition-colors", shown === i && "bg-muted/40")} />
                  <div className="relative flex flex-col-reverse gap-[2px]" style={{ height: `${max ? (total / max) * 100 : 0}%` }}>
                    {series.map((s, si) => {
                      const v = d[s.key] || 0;
                      if (!v) return null;
                      const top = series.slice(si + 1).every((t) => !(d[t.key] || 0));
                      return (
                        <div
                          key={s.key}
                          className={cn("w-full min-h-[2px]", top && "rounded-t-[4px]")}
                          style={{ flexGrow: v, flexBasis: 0, background: s.color, opacity: shown === null || shown === i ? 1 : 0.55 }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          {shown !== null && data[shown] ? (
            <Tooltip day={data[shown]} series={series} format={format} left={((shown + 0.5) / data.length) * 100} />
          ) : null}
        </div>
      </div>
      <div className="relative ml-10 mt-1.5 h-4 text-[10px] text-muted-foreground" aria-hidden>
        {tickIdx.map((i, n) => (
          <span
            key={`${i}-${n}`}
            className={cn("absolute whitespace-nowrap", n === 0 ? "left-0" : n === 2 ? "right-0" : "-translate-x-1/2")}
            style={n === 1 ? { left: `${((i + 0.5) / data.length) * 100}%` } : undefined}
          >
            {formatDay(data[i]?.date ?? "")}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{label}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <th scope="row">{d.date}</th>
              {series.map((s) => (
                <td key={s.key}>{d[s.key] || 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function Tooltip<K extends string>({
  day,
  series,
  format,
  left,
}: {
  day: { date: string } & Record<K, number>;
  series: Series<K>[];
  format: (v: number) => string;
  left: number;
}) {
  return (
    <div
      role="status"
      className="glass-2 pointer-events-none absolute bottom-full z-10 mb-2 min-w-36 -translate-x-1/2 rounded-lg px-3 py-2 text-xs shadow-lg"
      style={{ left: `clamp(4.5rem, ${left}%, calc(100% - 4.5rem))` }}
    >
      <p className="font-medium">{formatDay(day.date)}</p>
      <ul className="mt-1 space-y-0.5">
        {series.map((s) => (
          <li key={s.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="size-2 rounded-sm" style={{ background: s.color }} aria-hidden />
              {s.label}
            </span>
            <span className="font-medium tabular-nums">{format(day[s.key] || 0)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatDay(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Round the axis top up to 1/2/5 × 10ⁿ so gridline labels are readable numbers. */
function niceMax(v: number): number {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

/** Horizontal share bars for "top N" breakdowns: one hue, labels in ink, values right-aligned. */
export function ShareBars({ items, format = (v: number) => v.toLocaleString(), color = "var(--ai)" }: { items: { label: React.ReactNode; value: number; key: string }[]; format?: (v: number) => string; color?: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.key} className="text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate">{i.label}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{format(i.value)}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-muted/50" aria-hidden>
            <div className="h-full rounded-full" style={{ width: `${(i.value / max) * 100}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
