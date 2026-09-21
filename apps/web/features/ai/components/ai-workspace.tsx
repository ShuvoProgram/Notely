"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { aiApi } from "@/features/ai/api";
import { ChatPanel } from "@/features/ai/components/chat-panel";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { cn } from "@/lib/utils";

export function AIWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const threadId = params.get("thread");
  const queryClient = useQueryClient();
  const threads = useQuery({ queryKey: ["ai", "threads"], queryFn: aiApi.threads });
  const remove = useMutation({
    mutationFn: aiApi.deleteThread,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["ai", "threads"] });
      if (threadId === id) router.replace(pathname);
      toast.success("Conversation deleted");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const select = (id: string | null) => router.replace(id ? `${pathname}?thread=${id}` : pathname);

  return (
    <div data-full-bleed className="flex h-[calc(100dvh-4rem)] min-h-0">
      <aside aria-label="Conversations" className="glass hidden w-72 shrink-0 flex-col rounded-none border-y-0 border-l-0 md:flex">
        <div className="flex items-center justify-between px-4 py-4">
          <h2 className="text-base font-semibold tracking-tight">Conversations</h2>
          <Button size="icon-sm" variant="ghost" aria-label="New conversation" onClick={() => select(null)}>
            <Plus aria-hidden />
          </Button>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-3">
          {threads.isPending ? (
            <div className="space-y-2 p-1">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          ) : threads.data?.length ? (
            <ul className="space-y-0.5">
              {threads.data.map((t) => (
                <li key={t.id} className={cn("group flex items-center rounded-xl pr-1 transition-colors hover:bg-accent/50", t.id === threadId && "bg-accent/80 shadow-1 ring-1 ring-glass-border")}>
                  <button type="button" onClick={() => select(t.id)} aria-current={t.id === threadId ? "page" : undefined} className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <MessageSquare className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="truncate">{t.title}</span>
                  </button>
                  <Button size="icon-sm" variant="ghost" aria-label={`Delete conversation ${t.title}`} className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100" onClick={() => remove.mutate(t.id)}>
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-2 text-xs text-muted-foreground">No conversations yet.</p>
          )}
        </div>
      </aside>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-4 pb-28 sm:px-6 md:pb-4">
          <div className="mb-2 flex items-center justify-between md:hidden">
            <h1 className="text-lg font-semibold">AI Assistant</h1>
            <Button size="sm" variant="outline" onClick={() => select(null)}>
              <Plus aria-hidden /> New
            </Button>
          </div>
          <ChatPanel threadId={threadId} onThreadCreated={(id) => router.replace(`${pathname}?thread=${id}`)} />
        </div>
      </section>
    </div>
  );
}
