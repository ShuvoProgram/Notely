"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, Sparkles, Trash2, Workflow } from "@/components/icons";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { messageFor } from "@/features/auth/components/auth-form-error";

import { automationsApi } from "../api";
import { appName, scheduleText } from "../lib";
import type { Catalog, Template } from "../types";
import { AppChain, AutomationCard } from "./automation-card";
import { CreateWithAI } from "./create-with-ai";

function TemplateCard({ template, catalog, onDescribe }: { template: Template; catalog?: Catalog; onDescribe: (prompt: string) => void }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => automationsApi.deleteTemplate(template.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation-templates"] }),
    onError: (e) => toast.error(messageFor(e)),
  });
  return (
    <article className="flex flex-col gap-2 glass rounded-2xl p-4" aria-label={template.name}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium [overflow-wrap:anywhere]">{template.name}</h3>
          <p className="text-xs text-muted-foreground">{scheduleText({ ...template, starts_at: null })}</p>
        </div>
        {!template.builtin ? (
          <Button size="icon" variant="ghost" aria-label={`Delete template ${template.name}`} onClick={() => remove.mutate()}>
            <Trash2 className="size-4" />
          </Button>
        ) : null}
      </div>
      {template.description ? <p className="text-sm text-muted-foreground">{template.description}</p> : null}
      <AppChain apps={template.apps} catalog={catalog} />
      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        {template.available ? (
          <Button asChild size="sm" variant="outline">
            <Link href={`/app/automations/new?template=${template.id}`}>Use this</Link>
          </Button>
        ) : (
          template.missing_apps.map((app) => (
            <Button key={app} asChild size="sm" variant="outline">
              <Link href={`/app/settings/connections/${app}`}>Connect {appName(catalog, app)}</Link>
            </Button>
          ))
        )}
        {template.prompt && template.available ? (
          <Button size="sm" variant="ghost" className="text-link" onClick={() => onDescribe(template.prompt!)}>
            <Sparkles className="size-4" aria-hidden /> Customize with AI
          </Button>
        ) : null}
      </div>
    </article>
  );
}

/** What can I automate? What have I automated? Is it working? What happened last time? */
export function AutomationsDashboard() {
  const [ai, setAi] = React.useState<{ open: boolean; prompt: string }>({ open: false, prompt: "" });
  const [hero, setHero] = React.useState("");
  const automations = useQuery({
    queryKey: ["automations"],
    queryFn: automationsApi.list,
    refetchInterval: (q) => (q.state.data?.some((a) => a.running) ? 3000 : false),
  });
  const templates = useQuery({ queryKey: ["automation-templates"], queryFn: automationsApi.templates });
  const catalog = useQuery({ queryKey: ["automation-catalog"], queryFn: automationsApi.catalog });
  const describe = (prompt: string) => setAi({ open: true, prompt });

  const list = automations.data ?? [];
  const attention = list.filter((a) => a.pending_approvals > 0 || a.last_run?.status === "failed");
  const sortedTemplates = [...(templates.data ?? [])].sort((a, b) => Number(b.available) - Number(a.available) || Number(a.builtin) - Number(b.builtin));

  return (
    <div className="space-y-8">
      <PageHeader
        title="Automations"
        description="Tell Notely what you want done, and it takes care of it — on schedule, with your apps."
        actions={
          <>
            <Button onClick={() => describe("")}>
              <Sparkles /> Create with AI
            </Button>
            <Button asChild variant="outline">
              <Link href="/app/automations/new">
                <Plus /> Build manually
              </Link>
            </Button>
          </>
        }
      />

      {attention.length ? (
        <section className="flex items-start gap-3 rounded-2xl border border-warning/30 bg-warning/5 p-4 text-sm" aria-label="Needs attention">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <div>
            <p className="font-medium">{attention.length === 1 ? "One automation needs you" : `${attention.length} automations need you`}</p>
            <p className="text-muted-foreground">
              {attention.map((a, i) => (
                <React.Fragment key={a.id}>
                  {i > 0 ? ", " : ""}
                  <Link href={a.last_run ? `/app/automations/${a.id}?run=${a.last_run.id}` : `/app/automations/${a.id}`} className="text-foreground underline underline-offset-2">
                    {a.name}
                  </Link>
                  {a.pending_approvals ? " (waiting for approval)" : " (last run failed)"}
                </React.Fragment>
              ))}
            </p>
          </div>
        </section>
      ) : null}

      <section aria-labelledby="yours-title" className="space-y-3">
        <h2 id="yours-title" className="text-lg font-semibold">Your automations</h2>
        {automations.isPending ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2" aria-busy>
            <Skeleton className="h-52 rounded-2xl" />
            <Skeleton className="h-52 rounded-2xl" />
          </div>
        ) : automations.error ? (
          <p role="alert" className="text-sm text-destructive">{messageFor(automations.error)}</p>
        ) : list.length ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {list.map((automation) => (
              <AutomationCard key={automation.id} automation={automation} catalog={catalog.data} />
            ))}
          </div>
        ) : (
          <div className="rounded-3xl border border-ai/20 bg-ai-soft/20 p-5 sm:p-6">
            <EmptyState
              icon={Workflow}
              title="Tell Notely what you want done"
              description="For example: “Every weekday morning, summarize my important email and create tasks for anything I need to do.”"
              className="py-2"
            />
            <div className="mx-auto mt-3 max-w-xl space-y-2">
              <Textarea aria-label="What do you want done?" value={hero} onChange={(e) => setHero(e.target.value)} placeholder="Describe it in your own words…" className="min-h-20 bg-field" />
              <div className="flex flex-wrap justify-end gap-2">
                <Button asChild variant="ghost">
                  <Link href="/app/automations/new">Build it step by step</Link>
                </Button>
                <Button disabled={hero.trim().length < 3} onClick={() => describe(hero)}>
                  <Sparkles /> Create with AI
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      <section aria-labelledby="ideas-title" className="space-y-3">
        <div>
          <h2 id="ideas-title" className="text-lg font-semibold">What can I automate?</h2>
          <p className="text-sm text-muted-foreground">Ready-made starting points. Each one opens in the builder so you can change anything.</p>
        </div>
        {templates.isPending ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-40 rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {sortedTemplates.map((template) => (
              <TemplateCard key={template.id} template={template} catalog={catalog.data} onDescribe={describe} />
            ))}
          </div>
        )}
      </section>

      {ai.open ? <CreateWithAI open onOpenChange={(open) => setAi((s) => ({ ...s, open }))} initialPrompt={ai.prompt} /> : null}
    </div>
  );
}
