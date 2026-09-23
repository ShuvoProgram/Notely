"use client";

import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  Copy,
  Eye,
  FlaskConical,
  Filter,
  GitBranch,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  ShieldAlert,
  Trash2,
  Zap,
} from "@/components/icons";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { OPERATORS, actionOf, appIdOf, appName, dataSources, stepTitle, stepVerb, tokenize } from "../lib";
import type { ActionStep, BranchStep, Catalog, Condition, ConditionRule, Issue, RunStep, Step, Workflow } from "../types";
import { ActionFields, type FieldContext } from "./action-fields";
import { AppIcon } from "./app-icon";
import { ConditionEditor } from "./condition-editor";
import { DataView } from "./data-view";

export type InsertKind = "action" | "filter" | "branch";
export interface Slot {
  parent: string | null; // branch id, or null for the main flow
  arm: "then" | "otherwise" | null;
  index: number;
}

export interface BuilderContext {
  workflow: Workflow;
  catalog?: Catalog;
  samples: Record<string, unknown>;
  notes: FieldContext["notes"];
  issues: Issue[];
  testSteps: Record<string, RunStep>;
  labelFor: (path: string) => string;
  labelsVersion: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  update: (step: Step) => void;
  remove: (id: string) => void;
  move: (id: string, direction: -1 | 1) => void;
  duplicate: (id: string) => void;
  insert: (slot: Slot, kind: InsertKind) => void;
  changeAction: (id: string) => void;
  testThrough: (id: string) => void;
  testing: boolean;
}

function readable(value: unknown, labelFor: (p: string) => string): string {
  if (value == null || value === "") return "";
  // Lists (and rows of cells, e.g. Sheets) may hold data references at any depth.
  if (Array.isArray(value)) return value.map((item) => readable(item, labelFor)).filter(Boolean).join(", ");
  if (typeof value === "object") return Object.values(value).map((item) => readable(item, labelFor)).filter(Boolean).join(", ");
  if (typeof value !== "string") return String(value);
  return tokenize(value)
    .map((t) => ("ref" in t ? `[${labelFor(t.ref)}]` : t.text))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

export function conditionSentence(condition: Condition, labelFor: (p: string) => string): string {
  const parts = condition.rules
    .filter((r): r is ConditionRule => "operator" in r)
    .map((rule) => {
      const op = OPERATORS.find((o) => o.value === rule.operator);
      const left = readable(rule.left, labelFor) || "…";
      return op?.unary ? `${left} ${op.label}` : `${left} ${op?.label ?? rule.operator} ${readable(rule.right, labelFor) || "…"}`;
    });
  const sentence = parts.join(condition.match === "all" ? " and " : " or ");
  return condition.negate ? `not (${sentence})` : sentence;
}

function subtitle(step: Step, ctx: BuilderContext): string {
  if (step.kind !== "action") return conditionSentence(step.condition, ctx.labelFor);
  const action = actionOf(ctx.catalog, step);
  if (!action) return "";
  const shown = action.inputs
    .filter((f) => f.type !== "boolean" && step.inputs[f.key] != null && step.inputs[f.key] !== "")
    .slice(0, 2)
    .map((f) => {
      const value = step.inputs[f.key];
      if (f.type === "note") return ctx.notes.find((n) => n.id === value)?.title ?? "a note";
      if (f.type === "choice") return f.options?.find((o) => o.value === value)?.label ?? String(value);
      return readable(value, ctx.labelFor);
    });
  return shown.join(" · ");
}

function AddStep({ slot, ctx, compact }: { slot: Slot; ctx: BuilderContext; compact?: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant={compact ? "ghost" : "outline"}
          size="sm"
          aria-label="Add a step here"
          className={cn(
            compact
              ? "size-7 rounded-full border border-dashed border-glass-border-strong bg-background p-0 text-muted-foreground hover:border-ai hover:text-ai"
              : "border-dashed text-muted-foreground",
          )}
        >
          <Plus className="size-4" aria-hidden />
          {compact ? null : "Add a step"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="center" className="w-60">
        {/* Opened after the menu has closed: a dialog opened from inside the menu would be
            dismissed by the menu returning focus to its trigger. */}
        <DropdownMenuItem onSelect={() => setTimeout(() => ctx.insert(slot, "action"), 0)}>
          <Zap className="text-ai" /> Do something
          <span className="ml-auto text-xs text-muted-foreground">an app action</span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => ctx.insert(slot, "filter")}>
          <Filter className="text-warning" /> Only continue if…
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => ctx.insert(slot, "branch")}>
          <GitBranch className="text-info" /> Split into Yes / No paths
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Connector({ slot, ctx }: { slot: Slot; ctx: BuilderContext }) {
  return (
    <div className="relative flex h-10 items-center justify-center" aria-hidden={false}>
      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-glass-border-strong" aria-hidden />
      <span className="relative">
        <AddStep slot={slot} ctx={ctx} compact />
      </span>
    </div>
  );
}

function ActionSettings({ step, ctx }: { step: ActionStep; ctx: BuilderContext }) {
  const action = actionOf(ctx.catalog, step);
  const set = (patch: Partial<ActionStep>) => ctx.update({ ...step, ...patch });
  return (
    <details className="group rounded-xl border border-glass-border">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-sm text-muted-foreground">
        More options
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="grid gap-4 border-t border-glass-border p-3 sm:grid-cols-2">
        {action?.safety === "ask" ? (
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Before this step changes something outside Notely</Label>
            <Select value={step.approval ?? "ask"} onValueChange={(approval) => set({ approval: approval as ActionStep["approval"] })}>
              <SelectTrigger className="w-full" aria-label="Approval">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ask">Ask me first</SelectItem>
                <SelectItem value="auto">Do it automatically</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : action?.safety === "always_ask" ? (
          <p className="flex items-start gap-2 text-sm text-muted-foreground sm:col-span-2">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            This deletes or cancels something, so Notely always asks you first.
          </p>
        ) : null}
        <div className="space-y-1.5">
          <Label>If this step fails</Label>
          <Select value={step.on_error ?? "stop"} onValueChange={(on_error) => set({ on_error: on_error as ActionStep["on_error"] })}>
            <SelectTrigger className="w-full" aria-label="If this step fails">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="stop">Stop the automation</SelectItem>
              <SelectItem value="continue">Skip it and keep going</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Try again automatically</Label>
          <Select value={String(step.retries ?? 2)} onValueChange={(v) => set({ retries: Number(v) })}>
            <SelectTrigger className="w-full" aria-label="Retries">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="0">Don&apos;t retry</SelectItem>
              <SelectItem value="1">Once</SelectItem>
              <SelectItem value="2">Twice</SelectItem>
              <SelectItem value="3">Three times</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="text-xs text-muted-foreground sm:col-span-2">
          Step reference: <code className="rounded bg-muted px-1">{step.id}</code> · {action?.safety_text}
        </p>
      </div>
    </details>
  );
}

function StepCard({ step, index, total, ctx, position }: { step: Step; index: number; total: number; ctx: BuilderContext; position: string }) {
  const open = ctx.openId === step.id;
  const action = actionOf(ctx.catalog, step);
  const appId = appIdOf(step);
  const issues = ctx.issues.filter((i) => i.step_id === step.id);
  const tested = ctx.testSteps[step.id];
  const [renaming, setRenaming] = React.useState(false);
  const sources = React.useMemo(() => dataSources(ctx.workflow, step.id, ctx.catalog, ctx.samples), [ctx.workflow, step.id, ctx.catalog, ctx.samples]);
  const fieldCtx: FieldContext = { sources, catalog: ctx.catalog, notes: ctx.notes, labelFor: ctx.labelFor, labelsVersion: ctx.labelsVersion, issues: ctx.issues };
  const asksFirst = action && (action.safety === "always_ask" || (action.safety === "ask" && step.kind === "action" && step.approval !== "auto"));
  const verb = stepVerb(step, action);

  return (
    <div
      data-step={step.id}
      className={cn(
        "rounded-2xl border bg-card/70 shadow-1 transition-colors",
        open ? "border-ai/40" : "border-glass-border",
        step.enabled === false && "opacity-(--disabled-opacity)",
        issues.length && !open && "border-warning/40",
      )}
    >
      <div className="flex items-start gap-3 p-3 sm:p-4">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
          onClick={() => ctx.setOpenId(open ? null : step.id)}
          aria-expanded={open}
          aria-label={`${position}. ${stepTitle(step, ctx.catalog)}`}
        >
          <AppIcon appId={appId} catalog={ctx.catalog} size="md" />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {position}. {verb}
              {step.kind === "action" ? <span className="normal-case tracking-normal">· {appName(ctx.catalog, appId)}</span> : null}
            </span>
            <span className="mt-0.5 block font-medium leading-snug">{stepTitle(step, ctx.catalog)}</span>
            {subtitle(step, ctx) ? <span className="mt-0.5 line-clamp-2 block text-sm text-muted-foreground">{subtitle(step, ctx)}</span> : null}
            <span className="mt-1.5 flex flex-wrap gap-1.5">
              {step.enabled === false ? <Badge variant="outline">Turned off</Badge> : null}
              {asksFirst ? (
                <Badge variant="outline" className="gap-1 border-warning/40 text-warning">
                  <ShieldAlert className="size-3" aria-hidden /> Asks you first
                </Badge>
              ) : null}
              {issues.length ? (
                <Badge variant="outline" className="gap-1 border-warning/40 text-warning">
                  <AlertTriangle className="size-3" aria-hidden /> Needs a detail
                </Badge>
              ) : null}
              {tested ? (
                <Badge variant="outline" className={cn("gap-1", tested.status === "failed" ? "border-destructive/40 text-destructive" : "text-success")}>
                  {tested.status === "failed" ? <AlertTriangle className="size-3" aria-hidden /> : <CheckCircle2 className="size-3" aria-hidden />}
                  {tested.status === "failed" ? "Test failed" : tested.status === "skipped" ? "Didn't run in test" : "Tested"}
                </Badge>
              ) : null}
            </span>
          </span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon" aria-label={`Step ${position} options`}>
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {step.kind === "action" ? (
              <DropdownMenuItem disabled={ctx.testing} onSelect={() => ctx.testThrough(step.id)}>
                <FlaskConical /> Test up to this step
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem onSelect={() => { ctx.setOpenId(step.id); setRenaming(true); }}>
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => ctx.duplicate(step.id)}>
              <Copy /> Duplicate
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => ctx.update({ ...step, enabled: step.enabled === false })}>
              <Power /> {step.enabled === false ? "Turn on" : "Turn off"}
            </DropdownMenuItem>
            <DropdownMenuItem disabled={index === 0} onSelect={() => ctx.move(step.id, -1)}>
              <ArrowUp /> Move up
            </DropdownMenuItem>
            <DropdownMenuItem disabled={index === total - 1} onSelect={() => ctx.move(step.id, 1)}>
              <ArrowDown /> Move down
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setTimeout(() => ctx.remove(step.id), 0)}>
              <Trash2 /> Delete step
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {open ? (
        <div className="space-y-4 border-t border-glass-border p-3 sm:p-4">
          {issues.map((issue, i) => (
            <p key={i} className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {issue.message}{" "}
                {issue.fix_path ? (
                  <a href={issue.fix_path} className="font-medium underline underline-offset-2">
                    {issue.kind === "connect" ? "Connect" : "Fix"}
                  </a>
                ) : null}
              </span>
            </p>
          ))}
          {renaming ? (
            <div className="space-y-1.5">
              <Label htmlFor={`name-${step.id}`}>Step name</Label>
              <Input
                id={`name-${step.id}`}
                autoFocus
                value={step.name ?? ""}
                placeholder={stepTitle({ ...step, name: null }, ctx.catalog)}
                onChange={(e) => ctx.update({ ...step, name: e.target.value || null })}
                onBlur={() => setRenaming(false)}
                onKeyDown={(e) => e.key === "Enter" && setRenaming(false)}
              />
            </div>
          ) : null}
          {step.kind === "action" ? (
            action ? (
              <>
                {!action.available ? (
                  <p className="rounded-lg bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                    Connect {action.app_name} to use this step.
                  </p>
                ) : null}
                <ActionFields step={step} action={action} onChange={ctx.update} ctx={fieldCtx} />
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => ctx.changeAction(step.id)}>
                    Change action
                  </Button>
                  <Button type="button" variant="outline" size="sm" disabled={ctx.testing} onClick={() => ctx.testThrough(step.id)}>
                    <FlaskConical className="size-4" aria-hidden /> Test this step
                  </Button>
                </div>
                <ActionSettings step={step} ctx={ctx} />
              </>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">This action isn&apos;t available. Choose another one.</p>
                <Button type="button" variant="outline" size="sm" onClick={() => ctx.changeAction(step.id)}>
                  Choose an action
                </Button>
              </div>
            )
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium">{step.kind === "filter" ? "Only continue when…" : "Take the “Yes” path when…"}</p>
              <ConditionEditor
                idPrefix={step.id}
                value={step.condition}
                onChange={(condition) => ctx.update({ ...step, condition })}
                sources={sources}
                catalog={ctx.catalog}
                labelFor={ctx.labelFor}
                labelsVersion={ctx.labelsVersion}
              />
              {step.kind === "filter" ? (
                <p className="text-xs text-muted-foreground">If this isn&apos;t true, the run ends here — that counts as a normal finish, not a failure.</p>
              ) : null}
            </div>
          )}
          {tested ? (
            <div className="rounded-xl bg-muted/30 p-3 text-sm">
              <p className={cn("flex items-center gap-2 font-medium", tested.status === "failed" ? "text-destructive" : "text-success")}>
                {tested.status === "failed" ? <AlertTriangle className="size-4" aria-hidden /> : <CheckCircle2 className="size-4" aria-hidden />}
                {tested.error ?? tested.summary}
              </p>
              {tested.output != null ? (
                <details className="mt-2">
                  <summary className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground">
                    <Eye className="size-3.5" aria-hidden /> View the data it returned
                  </summary>
                  <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-glass-border bg-field p-3">
                    <DataView value={tested.output} />
                  </div>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Branch({ step, ctx, position }: { step: BranchStep; ctx: BuilderContext; position: string }) {
  return (
    // Paths stack vertically: side by side they would squeeze each step card too narrow.
    <div className="mt-2 grid gap-3 border-l-2 border-dashed border-glass-border-strong pl-3 sm:ml-5 sm:pl-4">
      {(["then", "otherwise"] as const).map((arm) => (
        <section key={arm} aria-label={arm === "then" ? "If yes" : "If no"} className="min-w-0 rounded-2xl bg-muted/15 p-2 sm:p-3">
          <p className={cn("mb-2 text-xs font-semibold uppercase tracking-wider", arm === "then" ? "text-success" : "text-muted-foreground")}>
            {arm === "then" ? "If yes" : "If no"}
          </p>
          <StepList steps={step[arm]} ctx={ctx} parent={step.id} arm={arm} prefix={`${position}${arm === "then" ? "a" : "b"}`} />
        </section>
      ))}
    </div>
  );
}

export function StepList({
  steps,
  ctx,
  parent = null,
  arm = null,
  prefix = "",
}: {
  steps: Step[];
  ctx: BuilderContext;
  parent?: string | null;
  arm?: "then" | "otherwise" | null;
  prefix?: string;
}) {
  if (!steps.length) {
    return (
      <div className="flex justify-center py-2">
        <AddStepEmpty slot={{ parent, arm, index: 0 }} ctx={ctx} nested={parent !== null} />
      </div>
    );
  }
  return (
    <div>
      {steps.map((step, index) => {
        const position = prefix ? `${prefix}.${index + 1}` : String(index + 1);
        return (
          <React.Fragment key={step.id}>
            {index > 0 ? <Connector slot={{ parent, arm, index }} ctx={ctx} /> : null}
            <StepCard step={step} index={index} total={steps.length} ctx={ctx} position={position} />
            {step.kind === "branch" ? <Branch step={step} ctx={ctx} position={position} /> : null}
          </React.Fragment>
        );
      })}
      <Connector slot={{ parent, arm, index: steps.length }} ctx={ctx} />
    </div>
  );
}

function AddStepEmpty({ slot, ctx, nested }: { slot: Slot; ctx: BuilderContext; nested: boolean }) {
  return nested ? (
    <AddStep slot={slot} ctx={ctx} />
  ) : (
    <div className="w-full rounded-2xl border border-dashed border-glass-border-strong p-6 text-center">
      <p className="font-medium">What should happen?</p>
      <p className="mb-3 text-sm text-muted-foreground">Add the first step, like “Find important Gmail” or “Create a task”.</p>
      <AddStep slot={slot} ctx={ctx} />
    </div>
  );
}
