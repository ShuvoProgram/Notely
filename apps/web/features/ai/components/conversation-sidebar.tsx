"use client";

import { ChevronDown, PanelLeftClose, PanelLeftOpen, Search, SquarePen, X } from "@/components/icons";
import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ConversationRow, groupOf, type ThreadActions, useThreadActivity } from "@/features/ai/components/conversation-list";
import type { AIThread } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/* ─────────────────────────────────────────────────────────
 * CONVERSATION SIDEBAR (AI page)
 * New conversation, then the searchable conversation history grouped by recency,
 * and a collapse to an icon rail that keeps icons aligned.
 *
 *   0ms   collapse: width eases 272 → 52, labels fade and drift left
 * 180ms   labels gone; icons never move
 *
 *   0ms   search: the "Chats" label fades, the field grows right → left
 * 180ms   field fills the row, cursor is in it
 * ───────────────────────────────────────────────────────── */

const EXPANDED = 272;
const COLLAPSED = 52;
const EASE = "ease-[cubic-bezier(0.16,1,0.3,1)]";

/* Collapsed/expanded is a per-browser convenience; it falls back to memory if storage is blocked. */
const STORAGE_KEY = "notely.ai.sidebar";
const listeners = new Set<() => void>();
let memory: boolean | null = null;
function readCollapsed(): boolean {
  if (memory !== null) return memory;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}
function writeCollapsed(value: boolean) {
  memory = value;
  try {
    window.localStorage.setItem(STORAGE_KEY, value ? "collapsed" : "open");
  } catch {
    // Storage blocked (private window); the in-memory value still applies for this visit.
  }
  listeners.forEach((l) => l());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

/** A hover highlight that glides between rows (`[data-row]`) instead of jumping. */
function GlideList({ children, className }: { children: React.ReactNode; className?: string }) {
  const [hl, setHl] = React.useState({ top: 0, left: 0, width: 0, height: 0, visible: false });
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const row = (e.target as Element).closest<HTMLElement>("[data-row]");
    if (!row || !e.currentTarget.contains(row)) return setHl((h) => (h.visible ? { ...h, visible: false } : h));
    const next = { top: row.offsetTop, left: row.offsetLeft, width: row.offsetWidth, height: row.offsetHeight, visible: true };
    setHl((h) => (h.visible && h.top === next.top && h.left === next.left && h.width === next.width && h.height === next.height ? h : next));
  };
  return (
    <div onPointerMove={onPointerMove} onPointerLeave={() => setHl((h) => ({ ...h, visible: false }))} className={cn("group/glide relative flex flex-col gap-px", className)}>
      <div
        aria-hidden
        className={cn("pointer-events-none absolute left-0 top-0 rounded-lg bg-accent/70 transition-[transform,width,height,opacity] duration-200", EASE, hl.visible ? "opacity-100" : "opacity-0")}
        style={{ transform: `translate(${hl.left}px, ${hl.top}px)`, width: hl.width, height: hl.height }}
      />
      {children}
    </div>
  );
}

function Copy({ collapsed, className, children }: { collapsed: boolean; className?: string; children: React.ReactNode }) {
  return (
    <span className={cn("min-w-0 truncate transition-[opacity,transform] duration-[180ms]", EASE, collapsed ? "-translate-x-2 opacity-0" : "opacity-100", className)}>
      {children}
    </span>
  );
}

const railRow = "relative z-10 mx-2 flex h-8 shrink-0 items-center gap-2 overflow-hidden rounded-lg px-2 text-left text-sm font-medium outline-none transition-[width,background-color,color,transform] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]";

function RailButton({ icon, label, collapsed, onClick }: { icon: React.ReactNode; label: string; collapsed: boolean; onClick: () => void }) {
  return (
    <button data-row type="button" onClick={onClick} title={collapsed ? label : undefined} className={cn(railRow, "text-foreground", collapsed ? "w-9" : "w-[calc(100%-1rem)]")}>
      <span className="grid size-5 shrink-0 place-items-center">{icon}</span>
      <Copy collapsed={collapsed}>{label}</Copy>
    </button>
  );
}

export function ConversationSidebar({
  threads,
  archived,
  loading,
  activeId,
  onNew,
  actions,
}: {
  threads: AIThread[] | undefined;
  archived: AIThread[] | undefined;
  loading: boolean;
  activeId: string | null;
  onNew: () => void;
  actions: ThreadActions;
}) {
  const collapsed = React.useSyncExternalStore(subscribe, readCollapsed, () => false);
  const [listOpen, setListOpen] = React.useState(true);
  const [archivedOpen, setArchivedOpen] = React.useState(false);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const searchRef = React.useRef<HTMLInputElement>(null);
  const [startOfToday] = React.useState(() => new Date().setHours(0, 0, 0, 0));

  React.useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery("");
  };

  const activity = useThreadActivity(React.useMemo(() => [...(threads ?? []), ...(archived ?? [])], [threads, archived]));
  // Relative times tick over once a minute (not on every render).
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const matches = React.useCallback(
    (t: AIThread) => {
      const q = query.trim().toLowerCase();
      return !q || t.title.toLowerCase().includes(q) || (t.last_message ?? "").toLowerCase().includes(q);
    },
    [query],
  );
  const groups = React.useMemo(() => {
    const visible = [...(threads ?? [])].filter(matches).sort((a, b) => b.last_activity_at.localeCompare(a.last_activity_at));
    const map = new Map<string, AIThread[]>();
    for (const t of visible) {
      const key = groupOf(t.last_activity_at, startOfToday);
      map.set(key, [...(map.get(key) ?? []), t]);
    }
    return [...map.entries()];
  }, [threads, matches, startOfToday]);
  const archivedVisible = React.useMemo(() => (archived ?? []).filter(matches), [archived, matches]);

  return (
    <aside
      aria-label="Conversations"
      data-collapsed={collapsed}
      className={cn("glass hidden shrink-0 overflow-hidden rounded-none border-y-0 border-l-0 transition-[width] duration-[280ms] md:flex", EASE)}
      style={{ width: collapsed ? COLLAPSED : EXPANDED }}
    >
      <div className="flex min-h-0 shrink-0 flex-col py-3" style={{ width: EXPANDED }}>
        {/* header: title + collapse; when collapsed only the expand control remains, where the first icon sits */}
        <div className="relative mb-2 h-9 shrink-0">
          <h2 className={cn("absolute left-4 top-1.5 text-base font-semibold tracking-tight transition-[opacity,transform] duration-[180ms]", EASE, collapsed ? "-translate-x-2 opacity-0" : "opacity-100")} aria-hidden={collapsed || undefined}>
            Conversations
          </h2>
          <button
            type="button"
            aria-label="Collapse sidebar"
            tabIndex={collapsed ? -1 : 0}
            aria-hidden={collapsed || undefined}
            onClick={() => {
              closeSearch();
              writeCollapsed(true);
            }}
            className={cn("absolute right-2 top-0.5 grid size-8 place-items-center rounded-lg text-muted-foreground transition-[opacity,background-color,color] duration-150 hover:bg-accent hover:text-foreground", collapsed && "pointer-events-none opacity-0")}
          >
            <PanelLeftClose className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Expand sidebar"
            tabIndex={collapsed ? 0 : -1}
            aria-hidden={!collapsed || undefined}
            onClick={() => writeCollapsed(false)}
            className={cn("absolute left-2 top-0.5 grid size-9 place-items-center rounded-lg text-muted-foreground transition-[opacity,background-color,color] duration-150 hover:bg-accent hover:text-foreground", !collapsed && "pointer-events-none opacity-0")}
          >
            <PanelLeftOpen className="size-4" aria-hidden />
          </button>
        </div>

        <GlideList>
          <RailButton icon={<SquarePen className="size-4" aria-hidden />} label="New conversation" collapsed={collapsed} onClick={onNew} />        </GlideList>

        <div
          inert={collapsed}
          className={cn("mt-3 flex min-h-0 flex-1 flex-col transition-opacity duration-[180ms]", collapsed ? "opacity-0" : "opacity-100")}
        >
          {/* "Chats" header ⇄ search field */}
          <div className="relative mx-2 mb-1 h-8 shrink-0">
            <button
              type="button"
              aria-expanded={listOpen}
              aria-hidden={searchOpen || undefined}
              tabIndex={searchOpen ? -1 : 0}
              onClick={() => setListOpen((o) => !o)}
              className={cn(
                "absolute inset-y-0 left-0 flex items-center gap-1 rounded-md px-2 text-xs font-medium text-muted-foreground transition-[opacity,transform] duration-[180ms] hover:text-foreground",
                EASE,
                searchOpen && "pointer-events-none -translate-x-1 opacity-0",
              )}
            >
              <ChevronDown className={cn("size-3.5 transition-transform duration-200", !listOpen && "-rotate-90")} aria-hidden />
              Chats
              {threads?.length ? <span className="tabular-nums text-tertiary">{threads.length}</span> : null}
            </button>
            <button
              type="button"
              aria-label="Search conversations"
              aria-expanded={searchOpen}
              tabIndex={searchOpen ? -1 : 0}
              onClick={() => {
                setListOpen(true);
                setSearchOpen(true);
              }}
              className={cn(
                "absolute right-0 top-0 z-10 grid size-8 place-items-center rounded-lg text-muted-foreground transition-[opacity,background-color,color,transform] duration-[180ms] hover:bg-accent hover:text-foreground active:scale-[0.96]",
                searchOpen && "pointer-events-none opacity-0",
              )}
            >
              <Search className="size-4" aria-hidden />
            </button>
            <div
              className={cn(
                "absolute right-0 top-0 z-20 flex h-8 items-center overflow-hidden rounded-lg bg-muted/70 text-muted-foreground ring-1 ring-glass-border transition-[width,opacity] duration-[180ms] focus-within:text-foreground",
                EASE,
                searchOpen ? "w-full opacity-100" : "pointer-events-none w-8 opacity-0",
              )}
            >
              <Search className="ml-2 size-3.5 shrink-0" aria-hidden />
              <input
                ref={searchRef}
                value={query}
                tabIndex={searchOpen ? 0 : -1}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") closeSearch();
                }}
                placeholder="Search conversations"
                aria-label="Search conversation history"
                className="ml-1.5 min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-placeholder"
              />
              <button
                type="button"
                aria-label="Close search"
                tabIndex={searchOpen ? 0 : -1}
                onClick={closeSearch}
                className="grid size-8 shrink-0 place-items-center rounded-lg transition-colors hover:bg-accent hover:text-foreground"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          </div>

          <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto pb-2">
            {!listOpen ? null : loading ? (
              <div className="space-y-2 px-3 py-1">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : groups.length ? (
              <GlideList>
                {groups.map(([label, items]) => (
                  <React.Fragment key={label}>
                    <p className="mx-2 px-2 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wide text-tertiary first:pt-1">{label}</p>
                    <ul className="flex flex-col gap-px">
                      {items.map((t) => (
                        <ConversationRow key={t.id} thread={t} active={t.id === activeId} activity={activity[t.id] ?? null} now={now} actions={actions} />
                      ))}
                    </ul>
                  </React.Fragment>
                ))}
              </GlideList>
            ) : (
              <p className="mx-2 px-2 py-2 text-xs text-muted-foreground">{query ? "No conversations found." : "No conversations yet."}</p>
            )}
            {archivedVisible.length ? (
              <div className="mt-3">
                <button
                  type="button"
                  aria-expanded={archivedOpen}
                  onClick={() => setArchivedOpen((o) => !o)}
                  className="mx-2 flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown className={cn("size-3.5 transition-transform duration-200", !archivedOpen && "-rotate-90")} aria-hidden />
                  Archived <span className="tabular-nums text-tertiary">{archivedVisible.length}</span>
                </button>
                {archivedOpen ? (
                  <GlideList>
                    <ul className="flex flex-col gap-px opacity-80">
                      {archivedVisible.map((t) => (
                        <ConversationRow key={t.id} thread={t} active={t.id === activeId} activity={activity[t.id] ?? null} now={now} actions={actions} />
                      ))}
                    </ul>
                  </GlideList>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </aside>
  );
}
