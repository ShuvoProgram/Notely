"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "@/components/icons";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { aiApi } from "@/features/ai/api";
import { ChatPanel } from "@/features/ai/components/chat-panel";
import { ConversationSidebar } from "@/features/ai/components/conversation-sidebar";
import { messageFor } from "@/features/auth/components/auth-form-error";

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
      <ConversationSidebar
        threads={threads.data}
        loading={threads.isPending}
        activeId={threadId}
        onSelect={select}
        onNew={() => select(null)}
        onDelete={(t) => remove.mutate(t.id)}
      />
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
