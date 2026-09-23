"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  CornerDownLeft,
  FileText,
  NotebookPen,
  PenLine,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  ShieldQuestion,
  Sparkles,
  Trash2,
  type IconComponent,
} from "@/components/icons";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { connectionsApi } from "@/features/connections/api";
import type { AIPlan, AISource, AIStep } from "@/lib/api/types";
import { providerLabel } from "@/lib/providers";
import { cn } from "@/lib/utils";

/*
 * How the assistant shows its work. Everything here is execution metadata the server streams
 * (plan steps, tool calls, verifications, sources) — never the model's private reasoning.
 *
 *   WorkingStatus  pixel loader + shimmering label + live elapsed timer, before words arrive
 *   PlanTrace      the declared plan as a collapsible checklist ("Worked for 12s")
 *   ToolTrace      tool calls as compact rows; each expands to its result and verification
 *   ReplyFooter    copy / retry, the sources behind the answer, and follow-up actions
 */

// --- timing ------------------------------------------------------------------------------------

function formatElapsed(ms: number): string {
  const s = Math.max(0, ms) / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
}

function formatDuration(ms: number): string {
  const s = Math.max(1, Math.round(ms / 1000));
  return s < 60 ? `${s} second${s === 1 ? "" : "s"}` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Milliseconds since `since`, re-rendered every 100ms. */
function useElapsed(since: number): number {
  const [now, setNow] = React.useState(since);
  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, []);
  return now - since;
}

// --- pixel loader ------------------------------------------------------------------------------

// A chevron wavefront over a 3×3 grid; the cycle is shorter than the sweep, so two fronts overlap.
const CHEVRON = Array.from({ length: 9 }, (_, i) => ((i % 3) + Math.abs(Math.floor(i / 3) - 1)) * 90);

export function PixelLoader({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("grid shrink-0 grid-cols-[repeat(3,4px)] gap-[1.5px]", className)}>
      {CHEVRON.map((delay, i) => (
        <span
          key={i}
          className="size-1 rounded-[1px] bg-ai opacity-15 motion-safe:animate-[notely-pixel_650ms_ease-in-out_infinite]"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function Shimmer({ children }: { children: React.ReactNode }) {
  return (
    <span className="bg-[linear-gradient(90deg,var(--muted-foreground)_35%,var(--foreground)_50%,var(--muted-foreground)_65%)] bg-[length:200%_100%] bg-clip-text text-transparent motion-safe:animate-[notely-shimmer-text_1.4s_linear_infinite] motion-reduce:text-muted-foreground">
      {children}
    </span>
  );
}

/** "▦ Searching your notes · 3.4s" — what the assistant is doing right now, and for how long. */
export function WorkingStatus({ label, since }: { label: string; since: number }) {
  const elapsed = useElapsed(since);
  return (
    <div role="status" className="flex w-fit items-center gap-2.5 py-0.5">
      <PixelLoader />
      <span className="text-[13px] font-medium">
        <Shimmer>{label}</Shimmer>
      </span>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{formatElapsed(elapsed)}</span>
    </div>
  );
}

// --- collapsible shell -------------------------------------------------------------------------

function Collapsible({ open, children }: { open: boolean; children: React.ReactNode }) {
  return (
    <div
      className="grid transition-[grid-template-rows,opacity] duration-300 ease-[cubic-bezier(0.23,1,0.32,1)]"
      style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

function TraceHeader({
  open,
  onToggle,
  icon,
  working,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  icon: React.ReactNode;
  working: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      onClick={onToggle}
      className="-mx-1.5 flex w-fit max-w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-muted/60"
    >
      <span className={cn("flex shrink-0", working ? "text-ai" : "text-muted-foreground")}>{icon}</span>
      <span className="min-w-0 truncate text-[13px] font-medium">{children}</span>
      <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform duration-300", open && "rotate-180")} aria-hidden />
    </button>
  );
}

// --- plan (ThinkingState) ----------------------------------------------------------------------

/** The declared plan: open while the run works, collapsed to "Worked for …" once it's done. */
export function PlanTrace({ plan, working, durationMs }: { plan: AIPlan; working: boolean; durationMs?: number }) {
  const [manual, setManual] = React.useState<boolean | null>(null);
  const open = manual ?? working;
  const done = plan.steps.filter((s) => s.status === "done").length;
  const heading = working
    ? plan.goal || `Working through ${plan.steps.length} steps`
    : durationMs
      ? `Worked for ${formatDuration(durationMs)} · ${done}/${plan.steps.length} steps`
      : `${plan.goal || "Plan"} · ${done}/${plan.steps.length} steps`;
  return (
    <section aria-label="Plan" className="flex flex-col">
      <TraceHeader open={open} onToggle={() => setManual(!open)} working={working} icon={<Sparkles className="size-4" aria-hidden />}>
        {working ? <Shimmer>{heading}</Shimmer> : <span className="text-muted-foreground">{heading}</span>}
      </TraceHeader>
      <Collapsible open={open}>
        <ol className="relative mt-1 ml-[7px] space-y-0.5 border-l border-glass-border py-1 pl-4">
          {plan.steps.map((step, i) => (
            <li
              key={`${i}-${step.title}`}
              data-status={step.status}
              className="flex min-h-7 items-center gap-2 text-[12.5px] motion-safe:animate-[notely-fade-up_320ms_cubic-bezier(0.23,1,0.32,1)_both]"
              style={{ animationDelay: `${i * 90}ms` }}
            >
              {step.status === "done" ? (
                <Check className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              ) : step.status === "active" ? (
                <span className="size-3 shrink-0 animate-spin rounded-full border-[1.5px] border-muted-foreground/30 border-t-ai" aria-hidden />
              ) : step.status === "waiting" ? (
                <span className="size-3 shrink-0 rounded-full border-[1.5px] border-warning" aria-hidden />
              ) : (
                <span className="size-3 shrink-0 rounded-full border-[1.5px] border-muted-foreground/30" aria-hidden />
              )}
              <span className={cn("min-w-0 truncate", step.status === "skipped" ? "text-muted-foreground line-through" : step.status === "done" ? "text-muted-foreground" : "font-medium")}>
                {step.title}
              </span>
              {step.status === "waiting" ? <span className="shrink-0 text-xs text-warning">needs your approval</span> : null}
            </li>
          ))}
        </ol>
      </Collapsible>
    </section>
  );
}

// --- tool calls (ToolChips) --------------------------------------------------------------------

function toolIcon(tool: string): IconComponent {
  const name = tool.toLowerCase();
  if (/delete|trash|remove|cancel/.test(name)) return Trash2;
  if (/send|post|reply|message/.test(name)) return Send;
  if (/create|append|update|write|draft|add|complete|upload|schedule/.test(name)) return PenLine;
  if (/read|get|open/.test(name)) return FileText;
  if (/plan/.test(name)) return Sparkles;
  return Search;
}

function toolApp(tool: string): string {
  return tool.includes("__") ? providerLabel(tool.split("__")[0]!) : "Notely";
}

/** Tool calls as compact rows: icon, what happened, a chip with the result; each row expands. */
export function ToolTrace({ steps, working }: { steps: AIStep[]; working: boolean }) {
  const [manual, setManual] = React.useState<boolean | null>(null);
  const [openRows, setOpenRows] = React.useState<Set<string>>(() => new Set());
  const open = manual ?? working;
  const failed = steps.filter((s) => s.status === "failed").length;
  const apps = [...new Set(steps.map((s) => toolApp(s.tool)))];
  const toggleRow = (id: string) =>
    setOpenRows((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <section aria-label="Tool calls" className="flex flex-col">
      <TraceHeader open={open} onToggle={() => setManual(!open)} working={working} icon={<Search className="size-4" aria-hidden />}>
        <span className="tabular-nums text-muted-foreground">
          {steps.length} tool call{steps.length === 1 ? "" : "s"} · {apps.join(", ")}
          {failed ? <span className="text-destructive"> · {failed} failed</span> : null}
        </span>
      </TraceHeader>
      <Collapsible open={open}>
        <div className="-mx-1 flex flex-col gap-0.5 px-1 pt-1 pb-1">
          {steps.map((step) => {
            const Icon = toolIcon(step.tool);
            const rowOpen = openRows.has(step.call_id);
            const detail = [step.result_preview, step.verification?.detail].filter(Boolean) as string[];
            return (
              <div key={step.call_id} className="motion-safe:animate-[notely-fade-up_300ms_cubic-bezier(0.23,1,0.32,1)_both]">
                <button
                  type="button"
                  aria-expanded={rowOpen}
                  disabled={!detail.length}
                  onClick={() => toggleRow(step.call_id)}
                  className="group/row flex h-7 w-full min-w-0 items-center gap-2 rounded-md px-1 text-left transition-colors enabled:hover:bg-muted/60"
                >
                  <span className="relative flex size-4 shrink-0 items-center justify-center text-muted-foreground">
                    {step.status === "running" ? (
                      <span className="size-3 animate-spin rounded-full border-[1.5px] border-muted-foreground/30 border-t-ai" aria-label="Running" />
                    ) : step.status === "failed" ? (
                      <AlertTriangle className="size-3.5 text-destructive" aria-label="Failed" />
                    ) : (
                      <>
                        <Icon className={cn("size-3.5 transition-opacity group-enabled/row:group-hover/row:opacity-0", rowOpen && "opacity-0")} aria-hidden />
                        {detail.length ? (
                          <ChevronDown
                            className={cn("absolute size-3.5 transition-[opacity,transform] group-hover/row:opacity-100", rowOpen ? "opacity-100" : "-rotate-90 opacity-0")}
                            aria-hidden
                          />
                        ) : null}
                      </>
                    )}
                  </span>
                  <span className={cn("shrink-0 text-[12.5px] font-medium", step.status === "failed" && "text-destructive")}>{step.label}</span>
                  <span className="inline-flex h-5.5 min-w-0 flex-1 items-center truncate rounded-md bg-muted/60 px-1.5 text-[11.5px] text-muted-foreground ring-1 ring-glass-border">
                    {step.status === "running" ? toolApp(step.tool) : step.result_preview || toolApp(step.tool)}
                  </span>
                  {step.verification ? (
                    step.verification.status === "verified" ? (
                      <ShieldCheck className="size-3.5 shrink-0 text-success" aria-label="Verified" />
                    ) : step.verification.status === "failed" ? (
                      <AlertTriangle className="size-3.5 shrink-0 text-destructive" aria-label="Check failed" />
                    ) : (
                      <ShieldQuestion className="size-3.5 shrink-0 text-muted-foreground" aria-label="Unverified" />
                    )
                  ) : null}
                </button>
                <Collapsible open={rowOpen}>
                  <div className="mt-0.5 mb-1 ml-2.5 flex flex-col gap-0.5 border-l border-glass-border py-0.5 pl-3.5">
                    {detail.map((line) => (
                      <span key={line} className="text-[11.5px] leading-relaxed text-muted-foreground">
                        {line}
                      </span>
                    ))}
                  </div>
                </Collapsible>
              </div>
            );
          })}
        </div>
      </Collapsible>
    </section>
  );
}

// --- reply footer (StreamingText) --------------------------------------------------------------

const FOLLOW_UPS = ["Save this as a note", "Turn this into tasks", "Make it shorter"];

function SourceIcon({ provider, logo, className }: { provider: string; logo?: string | null; className?: string }) {
  if (provider === "notely" || !logo) {
    return (
      <span className={cn("grid place-items-center rounded-full bg-primary/15 text-primary", className)}>
        <NotebookPen className="size-2.5" aria-hidden />
      </span>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={logo} alt="" className={cn("rounded-full bg-white object-contain p-px", className)} loading="lazy" />;
}

/** Copy / retry, the sources behind the answer, and (on the latest reply) follow-up actions. */
export function ReplyFooter({
  content,
  sources,
  onRetry,
  onFollowUp,
}: {
  content: string;
  sources: AISource[];
  onRetry?: () => void;
  onFollowUp?: (text: string) => void;
}) {
  const [sourcesOpen, setSourcesOpen] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const providers = useQuery({ queryKey: ["integrations", "providers"], queryFn: connectionsApi.providers, staleTime: 5 * 60_000 });
  const logos = new Map((providers.data ?? []).map((p) => [p.id, p.logo_url]));
  const byProvider = [...new Set(sources.map((s) => s.provider))];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy — your browser blocked clipboard access.");
    }
  };
  const iconButton = "flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground";

  return (
    <div className="motion-safe:animate-[notely-fade-up_350ms_cubic-bezier(0.23,1,0.32,1)_both]">
      <div className="flex items-center gap-0.5">
        <button type="button" aria-label={copied ? "Copied" : "Copy answer"} onClick={() => void copy()} className={iconButton}>
          {copied ? <Check className="size-3.5 text-success" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        </button>
        {onRetry ? (
          <button type="button" aria-label="Ask again" onClick={onRetry} className={iconButton}>
            <RotateCcw className="size-3.5" aria-hidden />
          </button>
        ) : null}
        {sources.length ? (
          <button
            type="button"
            aria-expanded={sourcesOpen}
            onClick={() => setSourcesOpen((o) => !o)}
            className="ml-1.5 flex items-center gap-1.5 rounded-md px-1.5 py-0.5 transition-colors hover:bg-muted"
          >
            <span className="flex -space-x-1">
              {byProvider.slice(0, 4).map((p) => (
                <SourceIcon key={p} provider={p} logo={logos.get(p)} className="size-4 shadow-[0_0_0_1.5px_var(--background)]" />
              ))}
            </span>
            <span className="text-xs text-muted-foreground">
              {sources.length} source{sources.length === 1 ? "" : "s"}
            </span>
          </button>
        ) : null}
      </div>

      <Collapsible open={sourcesOpen}>
        <ul aria-label="Sources" className="mt-1.5 flex flex-col rounded-xl border border-glass-border bg-muted/30 p-1">
          {sources.map((s) => {
            const inner = (
              <>
                <SourceIcon provider={s.provider} logo={logos.get(s.provider)} className="size-4" />
                <span className="min-w-0 truncate">{s.title}</span>
                <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{providerLabel(s.provider)}</span>
              </>
            );
            const cls = "flex items-center gap-2 rounded-md px-1.5 py-1 text-xs transition-colors hover:bg-muted";
            return (
              <li key={`${s.provider}:${s.object_id}`}>
                {!s.url ? (
                  <span className={cls}>{inner}</span>
                ) : s.provider === "notely" ? (
                  <Link href={s.url} className={cls}>
                    {inner}
                  </Link>
                ) : (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className={cls}>
                    {inner}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      </Collapsible>

      {onFollowUp ? (
        <div className="mt-2.5">
          <p className="text-xs font-medium text-muted-foreground">Follow-ups</p>
          <div className="mt-0.5 flex flex-col">
            {FOLLOW_UPS.map((text, i) => (
              <button
                key={text}
                type="button"
                onClick={() => onFollowUp(text)}
                className="-ml-1.5 flex items-center gap-2 border-b border-glass-border px-1.5 py-1.5 text-left text-[12.5px] transition-colors last:border-b-0 hover:bg-muted/60 motion-safe:animate-[notely-fade-up_350ms_cubic-bezier(0.23,1,0.32,1)_both]"
                style={{ animationDelay: `${i * 90}ms` }}
              >
                <CornerDownLeft className="size-3 shrink-0 text-muted-foreground" aria-hidden />
                {text}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
