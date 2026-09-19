"use client";

import { ArrowUp, Check, CircleDashed, Loader2, Sparkles, Square, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApprovalCard } from "@/features/ai/components/approval-card";
import { type LiveAssistant, type StepState, useChat } from "@/features/ai/use-chat";
import type { AIMessage, AISource } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Summarize what I wrote this week",
  "What open tasks do I have?",
  "Find my notes about pricing",
  "Turn my latest note into tasks",
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
            <div className="grid size-11 place-items-center rounded-xl bg-ai-soft text-ai">
              <Sparkles className="size-5" aria-hidden />
            </div>
            <h2 className="mt-4 text-base font-semibold">Ask anything about your notes</h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              I can search and read your notes and tasks. Anything that changes something waits for your approval first.
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
        className="relative mt-2 rounded-xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring"
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
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{message.content}</div>
      </li>
    );
  }
  return (
    <li className="flex gap-3">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-2">
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
        {live.steps.length ? <Steps steps={live.steps} waiting={waiting} /> : null}
        {live.text ? <Markdown text={live.text} /> : !live.steps.length && !waiting ? <p className="text-sm text-muted-foreground">Thinking…</p> : null}
      </div>
    </li>
  );
}

/** Safe execution metadata only — never chain-of-thought. */
function Steps({ steps, waiting }: { steps: StepState[]; waiting: boolean }) {
  return (
    <ul className="space-y-1 rounded-lg border bg-card/60 px-3 py-2 text-sm" aria-label="Progress">
      {steps.map((s) => (
        <li key={s.call_id} className="flex items-center gap-2">
          {s.status === "running" ? (
            <Loader2 className="size-3.5 animate-spin text-ai" aria-hidden />
          ) : s.status === "failed" ? (
            <XCircle className="size-3.5 text-destructive" aria-hidden />
          ) : (
            <Check className="size-3.5 text-success" aria-hidden />
          )}
          <span className={cn(s.status === "failed" && "text-destructive")}>{s.label}</span>
          {s.result_preview && s.status !== "running" ? <span className="text-xs text-muted-foreground">· {s.result_preview}</span> : null}
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

function Sources({ sources }: { sources: AISource[] }) {
  const providers = [...new Set(sources.map((s) => s.provider))];
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <span>
        Based on {sources.length} source{sources.length === 1 ? "" : "s"}
      </span>
      {providers.map((p) => (
        <Badge key={p} variant="outline" className="font-normal capitalize">
          {p}
        </Badge>
      ))}
      {sources.slice(0, 4).map((s) => (
        <Link key={`${s.provider}:${s.object_id}`} href={s.url} className="rounded-full bg-secondary px-2 py-0.5 hover:bg-accent">
          {s.title}
        </Link>
      ))}
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
