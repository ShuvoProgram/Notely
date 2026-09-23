"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, HelpCircle, Loader2, Pencil, Plug, RotateCcw, Sparkles, Zap } from "@/components/icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { ApiError } from "@/lib/api/client";

import { automationsApi } from "../api";
import type { Draft } from "../types";
import { DRAFT_KEY, fromDraft } from "./automation-builder";
import { FlowPreview } from "./flow-preview";

const EXAMPLES = [
  "Every weekday at 9 AM, check my important Gmail, summarize anything that needs attention, create tasks for me, and save the summary to my Daily Email Summary note.",
  "Every Friday at 4 PM, review my open tasks and write a weekly review note.",
  "Every morning, summarize today's meetings and send me a notification.",
];

/** "Tell Notely what you want done": describe it, review a plain-language preview, then go. */
export function CreateWithAI({ open, onOpenChange, initialPrompt = "" }: { open: boolean; onOpenChange: (open: boolean) => void; initialPrompt?: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = React.useState(initialPrompt);
  const catalog = useQuery({ queryKey: ["automation-catalog"], queryFn: automationsApi.catalog, enabled: open });
  const draft = useMutation({ mutationFn: () => automationsApi.draft(prompt.trim()) });
  const result: Draft | undefined = draft.data;

  const openInBuilder = (d: Draft) => {
    queryClient.setQueryData(DRAFT_KEY, d);
    onOpenChange(false);
    router.push("/app/automations/new?draft=1");
  };
  const activate = useMutation({
    mutationFn: (d: Draft) => automationsApi.create({ ...fromDraft(d), enabled: true }),
    onSuccess: (automation) => {
      void queryClient.invalidateQueries({ queryKey: ["automations"] });
      toast.success(`“${automation.name}” is on.`);
      onOpenChange(false);
      router.push(`/app/automations/${automation.id}`);
    },
    onError: (error, d) => {
      if (error instanceof ApiError && error.code === "AUTOMATION_NOT_READY") {
        toast.message("Almost there — finish a couple of details in the builder.");
        openInBuilder(d);
      } else toast.error(messageFor(error));
    },
  });

  const blocked = !result?.workflow || result.missing_apps.length > 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) draft.reset();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-5 text-ai" aria-hidden /> {result ? "Here's what Notely will do" : "What do you want done?"}
          </DialogTitle>
          <DialogDescription>
            {result ? "Nothing runs until you turn it on. You can change any step." : "Describe it in your own words. Notely only uses apps and actions it can really run."}
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="space-y-3">
            <Textarea
              aria-label="Describe your automation"
              autoFocus
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Every weekday morning, summarize my important email and create tasks for anything I need to do"
              className="min-h-28"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && prompt.trim().length >= 3) draft.mutate();
              }}
            />
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground">Try one of these:</p>
              {EXAMPLES.map((example) => (
                <button key={example} type="button" onClick={() => setPrompt(example)} className="block w-full rounded-lg border border-glass-border px-3 py-2 text-left text-sm text-muted-foreground hover:border-ai/40 hover:text-foreground">
                  {example}
                </button>
              ))}
            </div>
            {draft.error ? (
              <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {messageFor(draft.error)}
                {draft.error instanceof ApiError && typeof draft.error.details.settings_path === "string" ? (
                  <Link href={draft.error.details.settings_path} className="font-medium underline">
                    Set up AI
                  </Link>
                ) : null}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="font-semibold">{result.name}</p>
              {result.description ? <p className="text-sm text-muted-foreground">{result.description}</p> : null}
            </div>
            {result.missing_apps.map((app) => (
              <div key={app.app} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-warning/40 bg-warning/5 p-3 text-sm">
                <span className="flex items-center gap-2">
                  <Plug className="size-4 text-warning" aria-hidden /> To create this automation, {app.name} needs to be connected.
                </span>
                <Button asChild size="sm">
                  <Link href={app.connect_path}>Connect {app.name}</Link>
                </Button>
              </div>
            ))}
            {result.unsupported.map((u) => (
              <div key={u.reason} className="rounded-xl border border-glass-border bg-muted/30 p-3 text-sm">
                <p className="font-medium">Notely can&apos;t do that part yet</p>
                <p className="text-muted-foreground">{u.reason}</p>
                {u.suggestion ? <p className="mt-1">Here&apos;s what you can do instead: {u.suggestion}</p> : null}
              </div>
            ))}
            {result.workflow ? (
              <div className="glass rounded-2xl p-4">
                <FlowPreview
                  workflow={result.workflow}
                  catalog={catalog.data}
                  schedule={result.schedule_kind ? { schedule_kind: result.schedule_kind, schedule_config: result.schedule_config, starts_at: result.starts_at } : undefined}
                />
              </div>
            ) : null}
            {[...result.questions, ...result.issues.map((i) => i.message)].map((q) => (
              <p key={q} className="flex items-start gap-2 text-sm text-muted-foreground">
                <HelpCircle className="mt-0.5 size-4 shrink-0 text-info" aria-hidden /> {q}
              </p>
            ))}
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          {!result ? (
            <Button className="w-full sm:w-auto sm:ml-auto" disabled={prompt.trim().length < 3 || draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {draft.isPending ? "Building your automation…" : "Create automation"}
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => draft.reset()}>
                <RotateCcw /> Describe it differently
              </Button>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={!result.workflow} onClick={() => openInBuilder(result)}>
                  <Pencil /> Review and edit
                </Button>
                <Button disabled={blocked || result.issues.length > 0 || activate.isPending} onClick={() => activate.mutate(result)}>
                  {activate.isPending ? <Loader2 className="animate-spin" /> : <Zap />} Turn it on
                </Button>
              </div>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
