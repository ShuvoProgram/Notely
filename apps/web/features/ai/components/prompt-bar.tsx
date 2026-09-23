"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Check, CheckSquare, ChevronDown, Mic, NotebookPen, Plus, Settings2, Square } from "@/components/icons";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { messageFor } from "@/features/auth/components/auth-form-error";
import { aiApi } from "@/features/ai/api";
import { connectionsApi } from "@/features/connections/api";
import { cn } from "@/lib/utils";

/*
 * The AI chat composer: type @ for a source (Notes, Tasks, your connected apps), / for a ready
 * request, pick the chat model, dictate, send. ↑↓ + Enter/Tab picks from a menu, Esc closes it.
 * Every control is real: sources come from your connections, the model picker changes the model
 * the assistant uses, and dictation uses the browser's speech recognition.
 */

type Row = { key: string; name: string; desc: string; icon?: React.ReactNode; logo?: string | null; href?: string | null; connected?: boolean; insert: string };

const COMMANDS: Row[] = [
  { key: "summarize", name: "/summarize", desc: "What I wrote this week", insert: "Summarize what I wrote this week" },
  { key: "tasks", name: "/tasks", desc: "My open tasks, most urgent first", insert: "What open tasks do I have? Put the most urgent first." },
  { key: "plan", name: "/plan", desc: "Plan my day from tasks and calendar", insert: "Plan my day from my open tasks and today's calendar." },
  { key: "search", name: "/search", desc: "Search notes and connected apps", insert: "Find everything about " },
  { key: "follow-up", name: "/follow-up", desc: "Follow-up from my latest meeting note", insert: "Prepare a follow-up from my latest meeting note." },
  { key: "draft-email", name: "/draft-email", desc: "Draft an email (you approve before it's sent)", insert: "Draft an email to " },
];

const ROW_H = 36; // h-9: the gliding highlight is positioned from the row index, no measuring
const MODEL_ROW_H = 32; // h-8

/** The last @word or /word being typed, if any. */
function parseToken(draft: string): { kind: "at" | "slash"; query: string; start: number } | null {
  const match = /(^|\s)([@/])([\w-]*)$/.exec(draft);
  if (!match) return null;
  return { kind: match[2] === "@" ? "at" : "slash", query: match[3]!.toLowerCase(), start: match.index + match[1]!.length };
}

// Minimal typing for the Web Speech API (not in TypeScript's DOM lib everywhere).
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
};
function speechRecognition(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => {};

export function PromptBar({
  busy,
  onSend,
  onStop,
  compact = false,
  placeholder = "Ask anything… type @ for a source or / for a command",
}: {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  compact?: boolean;
  placeholder?: string;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = React.useState("");
  const [dismissed, setDismissed] = React.useState(false);
  const [plusOpen, setPlusOpen] = React.useState(false);
  const [modelOpen, setModelOpen] = React.useState(false);
  const [hover, setHover] = React.useState<{ key: string; index: number; engaged: boolean }>({ key: "", index: 0, engaged: false });
  const [modelHovered, setModelHovered] = React.useState<number | null>(null);
  const [listening, setListening] = React.useState(false);
  const [sweep, setSweep] = React.useState(0);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const recognitionRef = React.useRef<Recognition | null>(null);
  // Server render has no speech API; decide on the client without a hydration mismatch.
  const canDictate = React.useSyncExternalStore(
    noopSubscribe,
    () => speechRecognition() !== null,
    () => false,
  );

  const providers = useQuery({ queryKey: ["integrations", "providers"], queryFn: connectionsApi.providers, staleTime: 60_000 });
  const settings = useQuery({ queryKey: ["ai", "settings"], queryFn: aiApi.settings, staleTime: 60_000 });

  // --- menus -------------------------------------------------------------------------------
  const sources = React.useMemo<Row[]>(() => {
    const builtins: Row[] = [
      { key: "notes", name: "Notes", desc: "Your Notely notes", icon: <NotebookPen className="size-4" />, connected: true, insert: "@Notes " },
      { key: "tasks", name: "Tasks", desc: "Your Notely tasks", icon: <CheckSquare className="size-4" />, connected: true, insert: "@Tasks " },
    ];
    const apps = (providers.data ?? [])
      .filter((p) => p.id !== "mcp_server" && (p.connection || p.connect_methods.length > 0))
      .map<Row>((p) => {
        const connected = p.connection?.status === "connected" || p.connection?.status === "syncing";
        return {
          key: p.id,
          name: p.name,
          desc: p.description,
          logo: p.logo_url,
          connected,
          href: connected ? null : `/app/settings/connections/${p.id}`,
          insert: `@${p.name} `,
        };
      })
      .sort((a, b) => Number(b.connected) - Number(a.connected));
    return [...builtins, ...apps];
  }, [providers.data]);

  const token = dismissed ? null : parseToken(draft);
  const menu: "at" | "slash" | null = plusOpen ? "at" : token?.kind ?? null;
  const query = plusOpen ? "" : token?.query ?? "";
  const rows = menu === "at" ? sources.filter((s) => s.name.toLowerCase().includes(query)) : menu === "slash" ? COMMANDS.filter((c) => c.name.slice(1).startsWith(query)) : [];
  const menuKey = `${menu}:${query}`;
  const active = hover.key === menuKey ? Math.min(hover.index, Math.max(rows.length - 1, 0)) : 0;
  const engaged = hover.key === menuKey && hover.engaged;
  const setActive = (index: number, engage = true) => setHover({ key: menuKey, index, engaged: engage });

  // --- model -------------------------------------------------------------------------------
  const own = settings.data?.user_model?.enabled ? settings.data.user_model : null;
  const models = [{ id: "__default", label: "Workspace default" }, ...(settings.data?.models ?? [])];
  const currentModel = settings.data?.preferences.model ?? "__default";
  const modelLabel = own ? own.model : models.find((m) => m.id === currentModel)?.label ?? "Workspace default";
  const modelIndex = Math.max(0, models.findIndex((m) => m.id === currentModel));
  const saveModel = useMutation({
    mutationFn: (id: string) => aiApi.updateSettings({ ...settings.data!.preferences, model: id === "__default" ? null : id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai", "settings"] }),
    onError: (e) => toast.error(messageFor(e)),
  });
  const selectModel = (id: string) => {
    setModelOpen(false);
    if (id === currentModel) return;
    saveModel.mutate(id);
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) setSweep((n) => n + 1);
    inputRef.current?.focus();
  };

  // --- input -------------------------------------------------------------------------------
  const resize = (el: HTMLTextAreaElement | null) => {
    if (!el) return;
    const max = compact ? 120 : 200;
    el.style.height = "0px";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, compact ? 40 : 56), max)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  };
  const updateDraft = (next: string) => {
    setDraft(next);
    requestAnimationFrame(() => resize(inputRef.current));
  };

  const pick = (row: Row) => {
    if (menu === "at" && row.href) {
      window.location.assign(row.href); // not connected yet → take them to connect it
      return;
    }
    const base = token ? draft.slice(0, token.start) : draft;
    updateDraft(`${base}${row.insert}`);
    setPlusOpen(false);
    setDismissed(false);
    inputRef.current?.focus();
  };

  const closeMenus = () => {
    setPlusOpen(false);
    setModelOpen(false);
  };

  const send = () => {
    const text = draft.trim();
    if (!text || busy) return;
    onSend(text);
    updateDraft("");
    closeMenus();
  };

  // Clicking outside the composer closes open menus.
  React.useEffect(() => {
    if (!modelOpen && !plusOpen) return;
    const close = (event: PointerEvent) => {
      if (!(event.target as Element).closest("[data-promptbar]")) closeMenus();
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [modelOpen, plusOpen]);

  React.useEffect(() => () => recognitionRef.current?.stop(), []);

  const toggleDictation = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const Speech = speechRecognition();
    if (!Speech) return;
    const recognition = new Speech();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const heard = Array.from(event.results)
        .map((r) => r[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (heard) setDraft((current) => (current ? `${current.trimEnd()} ${heard}` : heard));
      requestAnimationFrame(() => resize(inputRef.current));
    };
    recognition.onerror = (event) => {
      if (event.error === "not-allowed") toast.error("Allow microphone access to dictate.");
    };
    recognition.onend = () => {
      setListening(false);
      inputRef.current?.focus();
    };
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  };

  const canSend = draft.trim().length > 0;
  const iconButton = "flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-[background-color,color,transform] duration-150 hover:bg-muted hover:text-foreground active:scale-[0.94]";

  return (
    <div data-promptbar className="relative mt-2">
      {/* ── @ sources / slash commands ─────────────────────── */}
      {menu ? (
        <div
          role="listbox"
          aria-label={menu === "at" ? "Sources" : "Commands"}
          onMouseLeave={() => setHover({ key: menuKey, index: active, engaged: false })}
          className="absolute inset-x-0 bottom-full z-20 mb-2 glass-2 rounded-xl p-1 motion-safe:animate-[notely-pop-in_180ms_cubic-bezier(0.23,1,0.32,1)_both]"
          style={{ transformOrigin: "bottom center" }}
        >
          <div className="relative max-h-72 overflow-y-auto">
            <span
              aria-hidden
              className="pointer-events-none absolute inset-x-0 rounded-md bg-muted transition-[top,opacity] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]"
              style={{ top: active * ROW_H, height: ROW_H, opacity: engaged && rows.length ? 1 : 0 }}
            />
            {rows.map((row, i) => (
              <button
                key={row.key}
                type="button"
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(row)}
                className="relative z-10 flex h-9 w-full items-center gap-2.5 rounded-md px-2 text-left"
              >
                {menu === "at" ? (
                  <span className="flex size-5.5 shrink-0 items-center justify-center text-muted-foreground">
                    {row.logo ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={row.logo} alt="" className="size-4 object-contain" loading="lazy" />
                    ) : (
                      row.icon
                    )}
                  </span>
                ) : null}
                <span className="shrink-0 text-[12.5px] font-medium text-foreground">{row.name}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{row.desc}</span>
                {menu === "at" && row.key !== "notes" && row.key !== "tasks" ? (
                  <span className={cn("shrink-0 text-xs font-medium", row.connected ? "text-success" : "text-ai")}>{row.connected ? "Connected" : "Connect"}</span>
                ) : null}
              </button>
            ))}
            {rows.length === 0 ? <div className="flex h-9 items-center px-2 text-xs text-muted-foreground">No matches for “{query}”</div> : null}
          </div>
          <div className="mt-1 border-t border-glass-border px-2 pt-1.5 pb-1 text-[11px] text-muted-foreground">
            {menu === "at" ? "Point the assistant at a source · ↑↓ to move, Enter to pick" : "Ready-made requests · ↑↓ to move, Enter to pick"}
          </div>
        </div>
      ) : null}

      {/* ── model menu (above the composer, under its trigger) ── */}
      {modelOpen ? (
        <div
          role="listbox"
          aria-label="Models"
          onMouseLeave={() => setModelHovered(null)}
          className="absolute bottom-full left-10 z-20 mb-2 w-56 glass-2 rounded-xl p-1 motion-safe:animate-[notely-pop-in_180ms_cubic-bezier(0.23,1,0.32,1)_both]"
          style={{ transformOrigin: "bottom left" }}
        >
          {own ? (
            <div className="space-y-1 p-2 text-xs">
              <p className="font-medium text-foreground">Your own model</p>
              <p className="text-muted-foreground">{own.model}</p>
              <Link href="/app/settings/ai" className="inline-flex items-center gap-1 text-ai hover:underline">
                <Settings2 className="size-3" aria-hidden /> Change in AI settings
              </Link>
            </div>
          ) : (
            <div className="relative">
              <span
                aria-hidden
                className="pointer-events-none absolute inset-x-0 rounded-md bg-muted transition-[top,opacity] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]"
                style={{ top: (modelHovered ?? modelIndex) * MODEL_ROW_H, height: MODEL_ROW_H, opacity: modelHovered !== null ? 1 : 0 }}
              />
              {models.map((m, i) => (
                <button
                  key={m.id}
                  type="button"
                  role="option"
                  aria-selected={m.id === currentModel}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setModelHovered(i)}
                  onClick={() => selectModel(m.id)}
                  className="relative z-10 flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-[12.5px] font-medium text-foreground"
                >
                  <span className="min-w-0 flex-1 truncate">{m.label}</span>
                  <Check className={cn("size-3.5 shrink-0", m.id === currentModel ? "text-ai" : "invisible")} aria-hidden />
                </button>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* ── composer ───────────────────────────────────────── */}
      <div className="glass-2 relative flex flex-col gap-2 rounded-2xl p-2.5 transition-shadow focus-within:glow-ai">
        {/* one-shot colour sweep when the model changes */}
        {sweep ? (
          <span key={sweep} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]">
            <span className="absolute inset-y-0 -left-1/2 w-1/2 animate-[notely-sweep_650ms_cubic-bezier(0.16,1,0.3,1)_forwards] bg-[linear-gradient(90deg,transparent,#ef4444,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#a855f7,transparent)] opacity-40 blur-md" />
          </span>
        ) : null}

        <textarea
          ref={inputRef}
          rows={1}
          value={draft}
          aria-label="Ask anything"
          placeholder={listening ? "Listening…" : placeholder}
          onChange={(e) => {
            updateDraft(e.target.value);
            setDismissed(false);
            setPlusOpen(false);
          }}
          onKeyDown={(e) => {
            if (menu && rows.length > 0) {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setActive((active + (e.key === "ArrowDown" ? 1 : rows.length - 1)) % rows.length);
                return;
              }
              if ((e.key === "Enter" && !e.shiftKey) || e.key === "Tab") {
                e.preventDefault();
                pick(rows[active]!);
                return;
              }
            }
            if (e.key === "Escape") {
              setDismissed(true);
              closeMenus();
              return;
            }
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          className={cn(
            "relative w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-foreground outline-none [overflow-wrap:anywhere] placeholder:text-placeholder",
            compact ? "min-h-10" : "min-h-14",
          )}
        />

        <div className="relative flex items-center gap-1">
          <button
            type="button"
            aria-label="Add a source"
            aria-expanded={plusOpen}
            onClick={() => {
              setModelOpen(false);
              setPlusOpen((open) => !open);
              inputRef.current?.focus();
            }}
            className={cn(iconButton, plusOpen && "bg-muted text-foreground")}
          >
            <Plus className="size-4" aria-hidden />
          </button>

          {/* model picker */}
          <div className="relative">
            <button
              type="button"
              aria-label="Choose model"
              aria-expanded={modelOpen}
              onClick={() => {
                setPlusOpen(false);
                setModelOpen((open) => !open);
              }}
              className="flex h-8 max-w-48 items-center gap-1 rounded-lg px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <span className="truncate">{settings.isPending ? "Model" : modelLabel}</span>
              <ChevronDown className="size-3 shrink-0" aria-hidden />
            </button>
          </div>

          <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">Enter to send · Shift+Enter for a new line</span>

          {canDictate ? (
            <button
              type="button"
              aria-label={listening ? "Stop dictation" : "Dictate"}
              aria-pressed={listening}
              onClick={toggleDictation}
              className={cn(iconButton, "ml-auto sm:ml-1", listening && "bg-ai-soft text-ai hover:bg-ai-soft hover:text-ai")}
            >
              {listening ? (
                <span className="flex h-3.5 items-center gap-[2.5px]" aria-hidden>
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="h-full w-[2.5px] rounded-full bg-current motion-safe:animate-[notely-eq_900ms_ease-in-out_infinite]" style={{ animationDelay: `${i * 150}ms` }} />
                  ))}
                </span>
              ) : (
                <Mic className="size-4" aria-hidden />
              )}
            </button>
          ) : null}

          {busy ? (
            <button type="button" onClick={onStop} aria-label="Stop" className={cn(iconButton, "bg-foreground text-background hover:bg-foreground/85 hover:text-background", !canDictate && "ml-auto sm:ml-1")}>
              <Square className="size-3.5" aria-hidden />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Send"
              disabled={!canSend}
              onClick={send}
              className={cn(
                "flex size-8 shrink-0 items-center justify-center rounded-lg transition-[background-color,color,transform] duration-200 enabled:active:scale-[0.94]",
                canSend ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
                !canDictate && "ml-auto sm:ml-1",
              )}
            >
              <ArrowUp className="size-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
