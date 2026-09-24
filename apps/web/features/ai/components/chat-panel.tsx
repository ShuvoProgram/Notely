"use client";

import { RotateCcw, Sparkles, Square, XCircle } from "@/components/icons";
import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { load as reloadThread } from "@/features/ai/chat-store";
import { PlanTrace, ReplyFooter, ToolTrace, WorkingStatus } from "@/features/ai/components/agent-trace";
import { ApprovalCard } from "@/features/ai/components/approval-card";
import { PromptBar } from "@/features/ai/components/prompt-bar";
import { type LiveAssistant, useChat } from "@/features/ai/use-chat";
import type { AIMessage } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * One conversation. Everything here (history, live reply, approval, error, busy) belongs to
 * `threadId` alone; replies in other conversations keep streaming in the background.
 */
export function ChatPanel({ threadId, noteId, onThreadCreated, compact = false }: { threadId: string | null; noteId?: string | null; onThreadCreated?: (id: string) => void; compact?: boolean }) {
  const { state, send, decide, stop, retry } = useChat(threadId, { onThreadCreated });
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [state.messages.length, state.live?.text, state.live?.steps.length, state.approval, state.error, state.stopped]);

  const empty = state.messages.length === 0 && !state.live;
  const lastAssistant = state.messages.map((m) => m.role).lastIndexOf("assistant");
  const unanswered = state.messages.at(-1)?.role === "user";
  const composer = <PromptBar busy={state.busy} compact={compact} onSend={(text) => void send(text, noteId)} onStop={() => void stop()} />;

  if (state.status === "loading" && empty) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex-1 space-y-5 px-1 py-4" aria-busy="true" aria-label="Loading conversation">
          <Skeleton className="ml-auto h-10 w-2/5 rounded-2xl" />
          <Skeleton className="h-16 w-4/5" />
          <Skeleton className="ml-auto h-10 w-1/3 rounded-2xl" />
        </div>
        {composer}
      </div>
    );
  }

  if (state.status === "load_error" && empty) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">{state.error ?? "Couldn't load this conversation."}</p>
        <Button size="sm" variant="outline" onClick={() => threadId && void reloadThread(threadId)}>
          <RotateCcw aria-hidden /> Try again
        </Button>
      </div>
    );
  }

  // A fresh conversation: a big heading with the composer right under it, centred on the page.
  if (empty && !compact) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center overflow-y-auto px-1 pb-[8vh]">
        <div className="w-full motion-safe:animate-[notely-fade-up_420ms_cubic-bezier(0.23,1,0.32,1)_both]">
          <h2 className="text-balance text-center text-3xl font-black leading-[1.08] tracking-[-0.03em] text-foreground sm:text-[2.6rem]">
            Think it. Ask it.
            <br />
            Notely does the rest.
          </h2>
          {/* <p className="mx-auto mt-3 max-w-md text-balance text-center text-sm text-muted-foreground sm:text-[15px]">
            Search, summarize and act across your notes, tasks and connected apps.
          </p> */}
          <div className="mt-8">{composer}</div>
          {state.error ? (
            <p role="alert" className="mt-3 text-center text-sm text-destructive">
              {state.error}
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-x-hidden overflow-y-auto px-1" aria-live="polite">
        {empty ? (
          <div className="flex h-full flex-col items-center justify-center py-6 text-center">
            <h2 className="text-balance text-lg font-bold tracking-tight">Ask anything about this note</h2>
            <p className="mt-1 max-w-xs text-balance text-sm text-muted-foreground">Summarize it, pull out tasks, or connect it to the rest of your work.</p>
          </div>
        ) : (
          <ol className="space-y-5 py-4">
            {state.messages.map((m, i) => {
              const latest = i === lastAssistant && !state.busy && !state.live;
              const askedWith = [...state.messages.slice(0, i)].reverse().find((x) => x.role === "user")?.content;
              return (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onRetry={latest && askedWith ? () => send(askedWith, noteId) : undefined}
                  onFollowUp={latest ? (text) => send(text, noteId) : undefined}
                />
              );
            })}
            {state.live ? <LiveBubble live={state.live} waiting={state.runStatus === "waiting_for_approval"} /> : null}
            {state.approval ? (
              <li>
                <ApprovalCard key={state.approval.approval_id} approval={state.approval} onDecide={decide} disabled={state.busy} />
              </li>
            ) : null}
            {state.error && !state.busy ? (
              <li role="alert" className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
                <XCircle className="size-4 shrink-0 text-destructive" aria-hidden />
                <span className="min-w-0 flex-1">{state.error}</span>
                {unanswered ? (
                  <Button size="sm" variant="outline" className="h-7 shrink-0" onClick={retry}>
                    <RotateCcw aria-hidden /> Retry
                  </Button>
                ) : null}
              </li>
            ) : null}
            {state.stopped && !state.busy && !state.error && unanswered ? (
              <li role="status" className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                <Square className="size-3.5 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1">You stopped this response.</span>
                <Button size="sm" variant="outline" className="h-7 shrink-0" onClick={retry}>
                  <RotateCcw aria-hidden /> Retry
                </Button>
              </li>
            ) : null}
          </ol>
        )}
      </div>

      {composer}
    </div>
  );
}

function MessageBubble({ message, onRetry, onFollowUp }: { message: AIMessage; onRetry?: () => void; onFollowUp?: (text: string) => void }) {
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
        {message.plan ? <PlanTrace plan={message.plan} working={false} durationMs={message.duration_ms} /> : null}
        {message.steps?.length ? <ToolTrace steps={message.steps} working={false} /> : null}
        <Markdown text={message.content} />
        <ReplyFooter content={message.content} sources={message.sources ?? []} onRetry={onRetry} onFollowUp={onFollowUp} />
      </div>
    </li>
  );
}

/** What the assistant is doing right now, in words: the running tool, the active plan step… */
function liveLabel(live: LiveAssistant, waiting: boolean): string {
  if (waiting) return "Waiting for your approval";
  if (live.notice) return live.notice;
  const running = [...live.steps].reverse().find((s) => s.status === "running");
  if (running) return running.label;
  const active = live.plan?.steps.find((s) => s.status === "active");
  if (active) return active.title;
  return live.steps.length ? "Putting it together" : "Thinking";
}

function LiveBubble({ live, waiting }: { live: LiveAssistant; waiting: boolean }) {
  return (
    <li className="flex gap-3">
      <AssistantAvatar pulse />
      <div className="min-w-0 flex-1 space-y-2">
        {live.plan ? <PlanTrace plan={live.plan} working /> : null}
        {live.steps.length ? <ToolTrace steps={live.steps} working={!live.text} /> : null}
        {live.text ? (
          <div className="relative">
            <Markdown text={live.text} />
            {!waiting ? <span aria-hidden className="ml-0.5 inline-block h-3.5 w-0.5 translate-y-0.5 rounded-full bg-foreground motion-safe:animate-pulse" /> : null}
          </div>
        ) : (
          <WorkingStatus label={liveLabel(live, waiting)} since={live.startedAt} />
        )}
      </div>
    </li>
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
