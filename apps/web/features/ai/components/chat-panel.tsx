"use client";

import { AlertTriangle, ArrowUp, Check, CircleDashed, ExternalLink, Loader2, ShieldCheck, ShieldQuestion, Sparkles, Square, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApprovalCard } from "@/features/ai/components/approval-card";
import { type LiveAssistant, type StepState, useChat } from "@/features/ai/use-chat";
import type { AIMessage, AIPlan, AISource, Verification } from "@/lib/api/types";
import { providerLabel } from "@/lib/providers";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Summarize what I wrote this week",
  "What open tasks do I have?",
  "Find everything about pricing across my apps",
  "Prepare a follow-up from my latest meeting note",
];

export function ChatPanel({ threadId, noteId, onThreadCreated, compact = false }: { threadId: string | null; noteId?: string | null; onThreadCreated?: (id: string) => void; compact?: boolean }) {
  const { state, send, decide, stop } = useChat(threadId);
  const [draft, setDraft] = React.useState("");
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const notified = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (state.threadId && !threadId && onThreadCreated && notified.current !== state.threadId) {
      notified.current = state.threadId;
      onThreadCreated(state.threadId);
    }
  }, [state.threadId, threadId, onThreadCreated]);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [state.messages.length, state.live?.text, state.live?.steps.length, state.approval]);

  const submit = () => {
    if (!draft.trim() || state.busy) return;
    send(draft, noteId);
    setDraft("");
  };

  const empty = state.messages.length === 0 && !state.live;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-1" aria-live="polite">
        {empty ? (
          <div className={cn("flex h-full flex-col items-center justify-center text-center", compact ? "py-6" : "py-16")}>
            <div className="grid size-12 place-items-center rounded-2xl bg-ai-soft text-ai ring-1 ring-ai/20">
              <Sparkles className="size-5" aria-hidden />
            </div>
            <h2 className="mt-4 text-base font-semibold">Ask anything about your notes</h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              I can search and read your notes, tasks and connected apps, and plan multi-step work across them. Anything that changes something waits for your approval first, and I check that it landed.
            </p>
            <ul className="mt-5 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <Button variant="outline" size="sm" onClick={() => send(s, noteId)} disabled={state.busy}>
                    {s}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ol className="space-y-5 py-4">
            {state.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {state.live ? <LiveBubble live={state.live} waiting={state.runStatus === "waiting_for_approval"} /> : null}
            {state.approval ? (
              <li>
                <ApprovalCard key={state.approval.approval_id} approval={state.approval} onDecide={decide} disabled={state.busy} />
              </li>
            ) : null}
            {state.error ? (
              <li role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
                <XCircle className="mt-0.5 size-4 text-destructive" aria-hidden /> {state.error}
              </li>
            ) : null}
          </ol>
        )}
      </div>

      <form
        className="glass-2 relative mt-2 rounded-2xl p-2 transition-shadow focus-within:glow-ai"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Textarea
          aria-label="Ask anything"
          placeholder="Ask anything…"
          value={draft}
          rows={compact ? 2 : 3}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          className="min-h-0 resize-none border-0 bg-transparent p-2 shadow-none focus-visible:ring-0"
        />
        <div className="flex items-center justify-between px-1 pb-1">
          <span className="text-[11px] text-muted-foreground">Enter to send · Shift+Enter for a new line</span>
          {state.busy ? (
            <Button type="button" size="sm" variant="outline" onClick={() => void stop()}>
              <Square className="size-3.5" aria-hidden /> Stop
            </Button>
          ) : (
            <Button type="submit" size="icon-sm" aria-label="Send" disabled={!draft.trim()}>
              <ArrowUp aria-hidden />
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: AIMessage }) {
  if (message.role === "user") {
    return (
      <li className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-1">{message.content}</div>
      </li>
    );
  }
  return (
    <li className="flex gap-3">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-2">
        {message.plan ? <Plan plan={message.plan} /> : null}
        {message.steps?.length ? <Steps steps={message.steps} waiting={false} /> : null}
        <Markdown text={message.content} />
        {message.sources?.length ? <Sources sources={message.sources} /> : null}
      </div>
    </li>
  );
}

function LiveBubble({ live, waiting }: { live: LiveAssistant; waiting: boolean }) {
  return (
    <li className="flex gap-3">
      <AssistantAvatar pulse />
      <div className="min-w-0 flex-1 space-y-2">
        {live.plan ? <Plan plan={live.plan} /> : null}
        {live.steps.length ? <Steps steps={live.steps} waiting={waiting} /> : null}
        {live.text ? <Markdown text={live.text} /> : !live.steps.length && !waiting ? <p className="text-sm text-muted-foreground">Thinking…</p> : null}
      </div>
    </li>
  );
}

/** The agent's declared plan, ticked off from execution metadata (PRD 62) — never chain-of-thought. */
function Plan({ plan }: { plan: AIPlan }) {
  const done = plan.steps.filter((s) => s.status === "done").length;
  return (
    <section aria-label="Plan" className="rounded-xl border border-ai/30 bg-ai-soft/40 px-3 py-2 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <Sparkles className="size-3.5 text-ai" aria-hidden />
        <span className="truncate">{plan.goal}</span>
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {done}/{plan.steps.length}
        </span>
      </p>
      <ol className="mt-1.5 space-y-1">
        {plan.steps.map((step, i) => (
          <li key={`${i}-${step.title}`} className={cn("flex items-center gap-2", step.status === "skipped" && "text-muted-foreground line-through")} data-status={step.status}>
            {step.status === "done" ? (
              <Check className="size-3.5 text-success" aria-hidden />
            ) : step.status === "active" ? (
              <Loader2 className="size-3.5 animate-spin text-ai" aria-hidden />
            ) : step.status === "waiting" ? (
              <CircleDashed className="size-3.5 text-warning" aria-hidden />
            ) : (
              <CircleDashed className="size-3.5 text-muted-foreground" aria-hidden />
            )}
            <span>{step.title}</span>
            {step.status === "waiting" ? <span className="text-xs text-muted-foreground">· needs your approval</span> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Safe execution metadata only — never chain-of-thought. */
function Steps({ steps, waiting }: { steps: StepState[]; waiting: boolean }) {
  return (
    <ul className="glass space-y-1 rounded-xl px-3 py-2 text-sm" aria-label="Progress">
      {steps.map((s) => (
        <li key={s.call_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {s.status === "running" ? (
            <Loader2 className="size-3.5 animate-spin text-ai" aria-hidden />
          ) : s.status === "failed" ? (
            <XCircle className="size-3.5 text-destructive" aria-hidden />
          ) : (
            <Check className="size-3.5 text-success" aria-hidden />
          )}
          <span className={cn(s.status === "failed" && "text-destructive")}>{s.label}</span>
          {s.result_preview && s.status !== "running" ? <span className="text-xs text-muted-foreground">· {s.result_preview}</span> : null}
          {s.verification ? <VerificationBadge verification={s.verification} /> : null}
        </li>
      ))}
      {waiting ? (
        <li className="flex items-center gap-2 text-muted-foreground">
          <CircleDashed className="size-3.5" aria-hidden /> Waiting for your approval
        </li>
      ) : null}
    </ul>
  );
}

/** Outcome of the read-back after a write. Honest by construction: it is set by the server, never by the model. */
function VerificationBadge({ verification }: { verification: Verification }) {
  const label = verification.status === "verified" ? "Verified" : verification.status === "failed" ? "Check failed" : "Unverified";
  const Icon = verification.status === "verified" ? ShieldCheck : verification.status === "failed" ? AlertTriangle : ShieldQuestion;
  return (
    <Badge variant={verification.status === "verified" ? "outline" : verification.status === "failed" ? "destructive" : "secondary"} className="gap-1 font-normal" title={verification.detail}>
      <Icon className="size-3" aria-hidden />
      {label}
    </Badge>
  );
}

/** "Based on N sources" (PRD 26). External items open in a new tab; items without a link are plain chips. */
function Sources({ sources }: { sources: AISource[] }) {
  const providers = [...new Set(sources.map((s) => s.provider))];
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" aria-label="Sources">
      <span>
        Based on {sources.length} source{sources.length === 1 ? "" : "s"}
      </span>
      {providers.map((p) => (
        <Badge key={p} variant="outline" className="font-normal">
          {providerLabel(p)}
        </Badge>
      ))}
      {sources.slice(0, 6).map((s) => {
        const cls = "inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 hover:bg-accent";
        const key = `${s.provider}:${s.object_id}`;
        if (!s.url) {
          return (
            <span key={key} className={cls}>
              {s.title}
            </span>
          );
        }
        if (s.provider !== "notely") {
          return (
            <a key={key} href={s.url} target="_blank" rel="noopener noreferrer" className={cls}>
              {s.title} <ExternalLink className="size-3" aria-hidden />
            </a>
          );
        }
        return (
          <Link key={key} href={s.url} className={cls}>
            {s.title}
          </Link>
        );
      })}
    </div>
  );
}

function AssistantAvatar({ pulse = false }: { pulse?: boolean }) {
  return (
    <div className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-ai-soft text-ai", pulse && "animate-pulse")} aria-hidden>
      <Sparkles className="size-3.5" />
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="notely-prose text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
