"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckSquare, FileText, Plug, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ProviderLogo } from "@/features/connections/components/marketplace";
import { useCreateNote, useNotesList } from "@/features/notes/hooks";
import { tasksApi } from "@/features/tasks/api";
import type { User } from "@/lib/api/types";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

/**
 * Home: a glanceable start page — jump back into recent notes, see what is due, and which
 * tools are connected. Everything here is a shortcut into a fuller screen.
 */
export function HomeDashboard({ user }: { user: User }) {
  const router = useRouter();
  const create = useCreateNote();
  const notes = useNotesList({ view: "active", limit: 6 });
  const tasks = useQuery({ queryKey: ["tasks", "open"], queryFn: () => tasksApi.list({ status: "open" }) });
  const providers = useQuery({ queryKey: ["integrations", "providers"], queryFn: connectionsApi.providers });

  const firstName = user.display_name.split(/\s+/)[0] ?? user.display_name;
  const recent = notes.data?.pages.flatMap((p) => p.notes).slice(0, 6) ?? [];
  const open = tasks.data?.slice(0, 5) ?? [];
  const connected = (providers.data ?? []).filter((p) => p.connection && p.connection.status !== "disconnected");

  const newNote = () =>
    create.mutate({}, { onSuccess: (n) => router.push(`/app/notes/${n.id}`), onError: (e) => toast.error(messageFor(e)) });

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        title={`${greeting()}, ${firstName}.`}
        description="Capture a thought, ask the assistant, or pick up where you left off."
        actions={
          <>
            <Button variant="outline" asChild className="rounded-full">
              <Link href="/app/ai">
                <Sparkles className="text-ai" aria-hidden /> Ask AI
              </Link>
            </Button>
            <Button onClick={newNote} disabled={create.isPending} className="rounded-full">
              <Plus aria-hidden /> New note
            </Button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="size-4 text-ai" aria-hidden /> Recent notes
            </CardTitle>
            <CardDescription>Saved automatically as you type.</CardDescription>
          </CardHeader>
          <CardContent>
            {notes.isPending ? (
              <div className="space-y-2" aria-busy>
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 rounded-xl" />
                ))}
              </div>
            ) : recent.length ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {recent.map((n) => (
                  <li key={n.id}>
                    <Link href={`/app/notes/${n.id}`} className="lift block rounded-xl bg-muted/40 px-3 py-2.5 ring-1 ring-glass-border outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      <p className="truncate text-sm font-medium">{n.title || "Untitled"}</p>
                      <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{n.excerpt || "No additional text"}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={FileText} className="py-6" title="No notes yet" description="Your first note is one click away." action={<Button size="sm" onClick={newNote}>New note</Button>} />
            )}
            {recent.length ? (
              <Button variant="link" asChild className="mt-2 px-0">
                <Link href="/app/notes">
                  All notes <ArrowRight aria-hidden />
                </Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckSquare className="size-4 text-ai" aria-hidden /> Open tasks
                {tasks.data?.length ? <Badge variant="secondary" className="ml-auto font-normal">{tasks.data.length}</Badge> : null}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {tasks.isPending ? (
                <Skeleton className="h-20 rounded-xl" />
              ) : open.length ? (
                <ul className="space-y-1.5 text-sm">
                  {open.map((t) => (
                    <li key={t.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 ring-1 ring-glass-border">
                      <span className="size-1.5 shrink-0 rounded-full bg-ai" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{t.title}</span>
                      {t.due_date ? <span className="shrink-0 text-xs text-muted-foreground">{t.due_date}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing due. Ask the assistant to extract tasks from a note.</p>
              )}
              <Button variant="link" asChild className="mt-2 px-0">
                <Link href="/app/tasks">
                  All tasks <ArrowRight aria-hidden />
                </Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Plug className="size-4 text-ai" aria-hidden /> Connected tools
              </CardTitle>
            </CardHeader>
            <CardContent>
              {providers.isPending ? (
                <Skeleton className="h-10 rounded-xl" />
              ) : connected.length ? (
                <ul className="flex flex-wrap gap-2">
                  {connected.map((p) => (
                    <li key={p.id}>
                      <Link href={`/app/connections/${p.id}`} className="flex items-center gap-2 rounded-full bg-muted/40 py-1 pl-1 pr-3 text-xs ring-1 ring-glass-border hover:bg-muted/70" title={p.name}>
                        <ProviderLogo provider={p} size="sm" className="size-6 rounded-md" /> {p.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Connect Gmail, Notion, Jira and more so the assistant can work across your tools.</p>
              )}
              <Button variant="link" asChild className="mt-2 px-0">
                <Link href="/app/connections">
                  {connected.length ? "Manage connections" : "Browse integrations"} <ArrowRight aria-hidden />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
