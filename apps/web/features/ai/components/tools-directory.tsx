"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Eye, Pencil, Search, Send, ShieldAlert, Trash2, type IconComponent } from "@/components/icons";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/layout/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { aiApi } from "@/features/ai/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { providerLabel } from "@/lib/providers";
import type { AssistantTool, RiskLevel } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Category = "all" | "notes" | "tasks" | "calendar" | "email" | "meetings" | "documents" | "chat" | "connections";

const CATEGORIES: { id: Category; label: string }[] = [
  { id: "all", label: "All" },
  { id: "notes", label: "Notes" },
  { id: "tasks", label: "Tasks" },
  { id: "calendar", label: "Calendar" },
  { id: "email", label: "Email" },
  { id: "meetings", label: "Meetings" },
  { id: "documents", label: "Documents" },
  { id: "chat", label: "Chat" },
  { id: "connections", label: "Connections" },
];

function categoryOf(t: AssistantTool): Exclude<Category, "all"> {
  const n = t.name.toLowerCase();
  if (/calendar|event/.test(n) || t.provider === "google_calendar") return "calendar";
  if (t.provider === "google_meet" || t.provider === "zoom") return "meetings";
  if (t.provider === "google_sheets" || t.provider === "google_docs") return "documents";
  if (t.provider === "slack" || t.provider === "microsoft_teams") return "chat";
  if (/mail|email/.test(n) || t.provider === "gmail" || t.provider === "outlook") return "email";
  if (t.provider !== "notely") return "connections";
  if (/task/.test(n)) return "tasks";
  return "notes";
}

/** "gmail__search_mail" → "Search mail"; "create_task" → "Create task". */
export function humanize(name: string): string {
  const local = name.includes("__") ? name.split("__").pop()! : name;
  const words = local.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const RISK: Record<RiskLevel, { label: string; hint: string; icon: IconComponent; tone: string; approval: boolean }> = {
  read: { label: "Available", hint: "Read-only · runs on its own", icon: Check, tone: "text-success", approval: false },
  write: { label: "Requires approval", hint: "Changes your data", icon: Pencil, tone: "text-warning", approval: true },
  external_communication: { label: "Requires approval", hint: "Sends something outside Notely", icon: Send, tone: "text-warning", approval: true },
  destructive: { label: "Requires approval", hint: "Deletes or overwrites data", icon: Trash2, tone: "text-destructive", approval: true },
};

/**
 * Everything the assistant can do right now, for this user. The list is the live tool
 * registry — built-in tools plus those from connected apps — so nothing is advertised that a
 * missing connector would make impossible. Approval-gated actions are marked as such.
 */
export function ToolsDirectory() {
  const settings = useQuery({ queryKey: ["ai", "settings"], queryFn: aiApi.settings });
  const [q, setQ] = React.useState("");
  const [category, setCategory] = React.useState<Category>("all");

  const tools = settings.data?.tools ?? [];
  const needle = q.trim().toLowerCase();
  const visible = tools.filter((t) => (category === "all" || categoryOf(t) === category) && (!needle || humanize(t.name).toLowerCase().includes(needle) || t.description.toLowerCase().includes(needle) || providerLabel(t.provider).toLowerCase().includes(needle)));
  const counts = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.id === "all" ? tools.length : tools.filter((t) => categoryOf(t) === c.id).length])) as Record<Category, number>;
  const approvals = tools.filter((t) => RISK[t.risk].approval).length;

  return (
    <div data-wide className="space-y-6">
      <div>
        <Link href="/app/settings/ai" className="inline-flex items-center gap-1 rounded text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden /> Assistant settings
        </Link>
        <h2 className="mt-3 text-xl font-semibold tracking-tight">What the assistant can do</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          {tools.length} tools available to you right now — {tools.length - approvals} read on their own, {approvals} wait for your approval. Connect more apps under{" "}
          <Link href="/app/settings/connections" className="underline underline-offset-2 hover:text-foreground">
            Connections
          </Link>{" "}
          to add tools.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label="Search tools" placeholder="Search tools…" value={q} onChange={(e) => setQ(e.target.value)} className="h-10 rounded-full bg-muted/40 pl-10" />
        </div>
        <Tabs value={category} onValueChange={(v) => setCategory(v as Category)}>
          <TabsList className="rounded-full">
            {CATEGORIES.filter((c) => c.id === "all" || counts[c.id] > 0).map((c) => (
              <TabsTrigger key={c.id} value={c.id} className="rounded-full">
                {c.label}
                <span className="ml-1.5 text-[11px] text-muted-foreground">{counts[c.id]}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {settings.isPending ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-3" aria-busy>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-2xl" />
          ))}
        </div>
      ) : settings.error ? (
        <p role="alert" className="text-sm text-destructive">
          {messageFor(settings.error)}
        </p>
      ) : !visible.length ? (
        <EmptyState icon={Search} title="No tools match" description={needle ? "Try another word." : "Nothing in this category yet — connect an app to add tools."} action={needle ? <Button variant="outline" size="sm" onClick={() => setQ("")}>Clear search</Button> : undefined} />
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-3">
          {visible.map((t) => {
            const risk = RISK[t.risk];
            const Icon = risk.icon;
            return (
              <li key={t.name} className="flex flex-col glass rounded-2xl p-4">
                <div className="flex items-start gap-3">
                  <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-muted/60", risk.tone)} aria-hidden>
                    {t.risk === "read" ? <Eye className="size-4" /> : <Icon className="size-4" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold leading-tight">{humanize(t.name)}</h3>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{t.description}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-glass-border pt-3 text-[11px]">
                  <Badge variant="secondary" className="font-normal">
                    {providerLabel(t.provider)}
                  </Badge>
                  <Badge variant="outline" className="font-normal capitalize text-muted-foreground">
                    {t.capability}
                  </Badge>
                  <span className={cn("ml-auto inline-flex items-center gap-1 font-medium", risk.tone)} title={risk.hint}>
                    {risk.approval ? <ShieldAlert className="size-3.5" aria-hidden /> : <Check className="size-3.5" aria-hidden />}
                    {risk.label}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
