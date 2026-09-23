"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, Loader2, Sparkles, X } from "@/components/icons";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { messageFor } from "@/features/auth/components/auth-form-error";

import { automationsApi } from "../api";
import type { AutomationInput, Draft } from "../types";

const IDEAS = [
  "Only continue when there's something new",
  "Also send me a notification when it's done",
  "Run it every weekday at 8 AM instead",
];

/** Change the automation by describing the change; the result is previewed before it applies. */
export function AIAssist({ form, onApply }: { form: AutomationInput; onApply: (draft: Draft) => void }) {
  const [prompt, setPrompt] = React.useState("");
  const draft = useMutation({
    mutationFn: () =>
      automationsApi.draft(prompt.trim(), {
        name: form.name,
        workflow: form.workflow,
        schedule_kind: form.schedule_kind,
        schedule_config: form.schedule_config,
        timezone: form.timezone,
      }),
  });
  const result = draft.data;

  return (
    <section className="space-y-3 rounded-2xl border border-ai/25 bg-ai-soft/30 p-4" aria-labelledby="ai-assist-title">
      <h2 id="ai-assist-title" className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="size-4 text-ai" aria-hidden /> Ask AI to change this
      </h2>
      {!result ? (
        <>
          <Textarea
            aria-label="Describe the change"
            placeholder="e.g. Add a condition so this only runs when I get more than 5 emails"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="min-h-20 bg-field"
          />
          <div className="flex flex-wrap gap-1.5">
            {IDEAS.map((idea) => (
              <button key={idea} type="button" onClick={() => setPrompt(idea)} className="rounded-full border border-glass-border bg-field px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground">
                {idea}
              </button>
            ))}
          </div>
          {draft.error ? <p role="alert" className="text-sm text-destructive">{messageFor(draft.error)}</p> : null}
          <Button size="sm" disabled={prompt.trim().length < 3 || draft.isPending || !form.workflow.steps.length} onClick={() => draft.mutate()}>
            {draft.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {draft.isPending ? "Working on it…" : "Suggest changes"}
          </Button>
        </>
      ) : (
        <div className="space-y-3 text-sm">
          {result.changes.length ? (
            <ul className="space-y-1">
              {result.changes.map((change) => (
                <li key={change} className="flex gap-2">
                  <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> {change}
                </li>
              ))}
            </ul>
          ) : null}
          {result.missing_apps.map((app) => (
            <p key={app.app} className="rounded-lg bg-field p-2">
              This needs {app.name}.{" "}
              <Link href={app.connect_path} className="font-medium text-ai underline underline-offset-2">
                Connect {app.name}
              </Link>
            </p>
          ))}
          {result.unsupported.map((u) => (
            <p key={u.reason} className="rounded-lg bg-field p-2 text-muted-foreground">
              {u.reason} {u.suggestion ? `Instead: ${u.suggestion}` : ""}
            </p>
          ))}
          {result.questions.map((q) => (
            <p key={q} className="text-muted-foreground">{q}</p>
          ))}
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!result.workflow}
              onClick={() => {
                onApply(result);
                draft.reset();
                setPrompt("");
              }}
            >
              <Check /> Apply changes
            </Button>
            <Button size="sm" variant="ghost" onClick={() => draft.reset()}>
              <X /> Discard
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">Applied changes aren&apos;t saved until you press Save.</p>
        </div>
      )}
    </section>
  );
}
