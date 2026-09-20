import { cn } from "@/lib/utils";

/**
 * Notely brand. The mark is a single continuous monoline "N" — thought (left upright) flowing
 * through the diagonal into action (right upright, in the brand green) — set in a dark tile so
 * it holds on any background. The wordmark is drawn with the same monoline grammar and inherits
 * `currentColor`, so it follows the theme. Source of truth for the exported files in
 * `public/brand/` is the same geometry.
 */

const STROKE = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function LogoMark({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden className={cn("shrink-0", className)}>
      <rect width="64" height="64" rx="15" fill="#1B1C21" />
      {/* hairline keeps the tile visible on the app's own dark background */}
      <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="14.25" fill="none" stroke="#FFFFFF" strokeOpacity="0.1" strokeWidth="1.5" />
      <path d="M18 48V16L46 48" stroke="#F3F4F7" strokeWidth="9" {...STROKE} />
      <path d="M46 48V16" stroke="#34D399" strokeWidth="9" {...STROKE} />
    </svg>
  );
}

/** Wordmark paths on a 360×135 grid (cap height 100, baseline y=100, stroke 14). */
const WORDMARK_D = [
  "M7 100V7L67 100V7",
  "M141 72A28 28 0 1 1 85 72A28 28 0 1 1 141 72",
  "M171 22V82Q171 100 189 100",
  "M155 44H189",
  "M201 72H257A28 28 0 1 0 249 92",
  "M283 7V100",
  "M301 44L327 100",
  "M353 44L321 128",
];

export function Wordmark({ className, height = 20 }: { className?: string; height?: number }) {
  // The y's descender hangs below the baseline; height maps the 135-unit box.
  return (
    <svg viewBox="0 0 360 135" height={height} width={(360 / 135) * height} aria-hidden className={cn("shrink-0", className)}>
      {WORDMARK_D.map((d) => (
        <path key={d} d={d} stroke="currentColor" strokeWidth="14" {...STROKE} />
      ))}
    </svg>
  );
}

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-foreground", className)}>
      <LogoMark />
      {compact ? null : <Wordmark className="-mb-1" />}
      <span className="sr-only">Notely AI</span>
    </span>
  );
}
