"use client";

import { Clock } from "@/components/icons";

import { cn } from "@/lib/utils";

import { actionOf, appIdOf, appName, referenceLabel, scheduleText, stepTitle, stepVerb } from "../lib";
import type { Catalog, Schedule, Step, Workflow } from "../types";
import { AppIcon } from "./app-icon";
import { conditionSentence } from "./step-list";

function Steps({ steps, workflow, catalog, depth }: { steps: Step[]; workflow: Workflow; catalog?: Catalog; depth: number }) {
  const labelFor = (path: string) => referenceLabel(path, workflow, catalog);
  return (
    <ol className={cn("space-y-2", depth > 0 && "mt-2 border-l-2 border-dashed border-glass-border-strong pl-3")}>
      {steps.map((step) => {
        const action = actionOf(catalog, step);
        const appId = appIdOf(step);
        return (
          <li key={step.id} className="text-sm">
            <div className="flex items-start gap-2.5">
              <AppIcon appId={appId} catalog={catalog} size="sm" />
              <div className="min-w-0">
                <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {stepVerb(step, action)}
                  {step.kind === "action" ? ` · ${appName(catalog, appId)}` : ""}
                </p>
                <p className="font-medium">{stepTitle(step, catalog)}</p>
                {step.kind !== "action" ? <p className="text-muted-foreground">{conditionSentence(step.condition, labelFor)}</p> : null}
              </div>
            </div>
            {step.kind === "branch" ? (
              <div className="ml-10 grid gap-2">
                {(["then", "otherwise"] as const).map((arm) => (
                  <div key={arm}>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{arm === "then" ? "If yes" : "If no"}</p>
                    {step[arm].length ? (
                      <Steps steps={step[arm]} workflow={workflow} catalog={catalog} depth={depth + 1} />
                    ) : (
                      <p className="text-xs text-muted-foreground">Nothing</p>
                    )}
                  </div>
                ))}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/** A plain-language picture of an automation: when it runs, then each step. */
export function FlowPreview({ workflow, schedule, catalog }: { workflow: Workflow; schedule?: Pick<Schedule, "schedule_kind" | "schedule_config" | "starts_at">; catalog?: Catalog }) {
  return (
    <div className="space-y-3">
      {schedule ? (
        <div className="flex items-center gap-2.5 text-sm">
          <span className="grid size-8 place-items-center rounded-lg bg-muted/60 text-muted-foreground" aria-hidden>
            <Clock className="size-4" />
          </span>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">When</p>
            <p className="font-medium">{scheduleText(schedule)}</p>
          </div>
        </div>
      ) : null}
      <Steps steps={workflow.steps} workflow={workflow} catalog={catalog} depth={0} />
    </div>
  );
}
