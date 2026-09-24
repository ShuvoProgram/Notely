"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText, Plus } from "@/components/icons";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { aiApi } from "@/features/ai/api";
import { forget, setChatActivityListener } from "@/features/ai/chat-store";
import { ChatPanel } from "@/features/ai/components/chat-panel";
import { ConversationRow, type ThreadActions, useThreadActivity } from "@/features/ai/components/conversation-list";
import { ConversationSidebar } from "@/features/ai/components/conversation-sidebar";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { AIThread } from "@/lib/api/types";

export function AIWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  // The URL is the source of truth for the open conversation, so a reload restores it.
  const threadId = params.get("thread");
  const queryClient = useQueryClient();
  const threads = useQuery({ queryKey: ["ai", "threads"], queryFn: () => aiApi.threads() });
  const archived = useQuery({ queryKey: ["ai", "threads", "archived"], queryFn: () => aiApi.threads({ archived: true }) });
  const [confirmDelete, setConfirmDelete] = React.useState<AIThread | null>(null);
  const [mobileListOpen, setMobileListOpen] = React.useState(false);

  // Any run starting or settling, in any conversation, refreshes the list (order, previews,
  // activity) and whatever the assistant may have changed.
  React.useEffect(() => {
    setChatActivityListener(() => {
      void queryClient.invalidateQueries({ queryKey: ["ai", "threads"] });
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
    });
    return () => setChatActivityListener(null);
  }, [queryClient]);

  const currentRef = React.useRef(threadId);
  React.useEffect(() => {
    currentRef.current = threadId;
  }, [threadId]);
  const select = React.useCallback((id: string | null) => router.replace(id ? `${pathname}?thread=${id}` : pathname), [router, pathname]);
  // A new conversation gets its id when its first message is sent; follow it only if the user
  // is still looking at the draft (they may have switched away while it was being created).
  const onThreadCreated = React.useCallback(
    (id: string) => {
      if (currentRef.current === null) select(id);
    },
    [select],
  );

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => aiApi.updateThread(id, { title }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai", "threads"] }),
    onError: (e) => toast.error(messageFor(e)),
  });
  const archive = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => aiApi.updateThread(id, { archived }),
    onSuccess: (_, { archived }) => {
      void queryClient.invalidateQueries({ queryKey: ["ai", "threads"] });
      toast.success(archived ? "Conversation archived" : "Conversation restored");
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: aiApi.deleteThread,
    onSuccess: (_, id) => {
      forget(id);
      void queryClient.invalidateQueries({ queryKey: ["ai", "threads"] });
      if (currentRef.current === id) select(null);
      setConfirmDelete(null);
      toast.success("Conversation deleted");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const actions: ThreadActions = {
    onSelect: (id) => {
      setMobileListOpen(false);
      select(id);
    },
    onRename: (t, title) => rename.mutate({ id: t.id, title }),
    onArchive: (t, value) => archive.mutate({ id: t.id, archived: value }),
    onDelete: (t) => setConfirmDelete(t),
  };

  return (
    <div data-full-bleed className="flex h-[calc(100dvh-4rem-var(--mobile-nav-space))] min-h-0">
      <ConversationSidebar threads={threads.data} archived={archived.data} loading={threads.isPending} activeId={threadId} onNew={() => select(null)} actions={actions} />
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-4 sm:px-6">
          <div className="mb-2 flex items-center justify-between gap-2 md:hidden">
            <Button size="sm" variant="outline" onClick={() => setMobileListOpen(true)}>
              <MessageSquareText aria-hidden /> Chats
            </Button>
            <Button size="sm" variant="outline" onClick={() => select(null)}>
              <Plus aria-hidden /> New
            </Button>
          </div>
          {/* Keyed by conversation: the composer's draft and scroll position never carry over. */}
          <ChatPanel key={threadId ?? "new"} threadId={threadId} onThreadCreated={onThreadCreated} />
        </div>
      </section>

      <MobileConversations open={mobileListOpen} onOpenChange={setMobileListOpen} threads={threads.data} activeId={threadId} actions={actions} />

      <ConfirmDialog
        open={confirmDelete !== null}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title="Delete this conversation?"
        description={
          <>
            “{confirmDelete?.title}” and all its messages will be permanently deleted. A reply that is still being written is stopped.
          </>
        }
        confirmLabel="Delete"
        pending={remove.isPending}
        onConfirm={() => confirmDelete && remove.mutate(confirmDelete.id)}
      />
    </div>
  );
}

function MobileConversations({
  open,
  onOpenChange,
  threads,
  activeId,
  actions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  threads: AIThread[] | undefined;
  activeId: string | null;
  actions: ThreadActions;
}) {
  const activity = useThreadActivity(threads);
  const [now] = React.useState(() => Date.now());
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[85vw] max-w-xs p-0">
        <SheetHeader className="px-4 pt-4">
          <SheetTitle>Conversations</SheetTitle>
        </SheetHeader>
        <ul className="flex flex-col gap-px overflow-y-auto pb-4">
          {(threads ?? []).map((t) => (
            <ConversationRow key={t.id} thread={t} active={t.id === activeId} activity={activity[t.id] ?? null} now={now} actions={actions} />
          ))}
          {threads && !threads.length ? <li className="px-4 py-2 text-sm text-muted-foreground">No conversations yet.</li> : null}
        </ul>
      </SheetContent>
    </Sheet>
  );
}
