"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { NoteSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import type { DataSource } from "../lib";
import type { ActionSpec, ActionStep, Catalog, InputSpec, Issue } from "../types";
import { TokenField } from "./token-field";

export interface FieldContext {
  sources: DataSource[];
  catalog?: Catalog;
  notes: NoteSummary[];
  labelFor: (path: string) => string;
  labelsVersion: string;
  issues: Issue[];
}

function text(value: unknown): string {
  if (value == null) return "";
  // One line per item; a row of cells (Sheets) shows as its cells separated by " | ".
  if (Array.isArray(value)) return value.map((item) => (Array.isArray(item) ? item.map(String).join(" | ") : String(item))).join("\n");
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function Field({ spec, step, set, ctx }: { spec: InputSpec; step: ActionStep; set: (value: unknown) => void; ctx: FieldContext }) {
  const id = `field-${step.id}-${spec.key}`;
  const value = step.inputs[spec.key];
  const invalid = ctx.issues.some((i) => i.step_id === step.id && i.field === spec.key);
  const label = (
    <Label htmlFor={id} className="text-sm">
      {spec.label}
      {!spec.required && spec.type !== "boolean" ? <span className="font-normal text-muted-foreground"> (optional)</span> : null}
    </Label>
  );
  let control: React.ReactNode;
  if (spec.type === "choice") {
    control = (
      <Select value={String(value ?? spec.default ?? "")} onValueChange={set}>
        <SelectTrigger id={id} className={cn("w-full", invalid && "border-destructive/60")}>
          <SelectValue placeholder="Choose…" />
        </SelectTrigger>
        <SelectContent>
          {spec.options?.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  } else if (spec.type === "boolean") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-glass-border px-3 py-2">
        {label}
        <Switch id={id} checked={Boolean(value ?? spec.default)} onCheckedChange={set} />
      </div>
    );
  } else if (spec.type === "note") {
    const current = typeof value === "string" ? value : "";
    control = (
      <Select value={current} onValueChange={set}>
        <SelectTrigger id={id} className={cn("w-full", invalid && "border-destructive/60")} aria-label={spec.label}>
          <SelectValue placeholder="Choose a note…" />
        </SelectTrigger>
        <SelectContent>
          {ctx.notes.length ? (
            ctx.notes.map((note) => (
              <SelectItem key={note.id} value={note.id}>
                {note.title || "Untitled"}
              </SelectItem>
            ))
          ) : (
            <p className="px-2 py-3 text-sm text-muted-foreground">You don&apos;t have any notes yet.</p>
          )}
        </SelectContent>
      </Select>
    );
  } else if (spec.type === "number" && !text(value).includes("{{")) {
    control = (
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        value={text(value ?? spec.default)}
        onChange={(e) => set(e.target.value === "" ? null : Number(e.target.value))}
        aria-invalid={invalid || undefined}
      />
    );
  } else {
    control = (
      <TokenField
        id={id}
        aria-label={spec.label}
        value={text(value)}
        onChange={(next) => set(spec.type === "list" && !next.includes("{{") ? next.split("\n").filter((l) => l.trim()) : next)}
        labelFor={ctx.labelFor}
        labelsVersion={ctx.labelsVersion}
        sources={ctx.sources}
        catalog={ctx.catalog}
        multiline={spec.type === "long_text" || spec.type === "list"}
        placeholder={spec.placeholder ?? (spec.type === "list" ? "One item per line, or insert a list" : spec.type === "date" ? "YYYY-MM-DD, or insert a date" : undefined)}
        mappable={spec.mappable}
        invalid={invalid}
      />
    );
  }
  return (
    <div className="space-y-1.5">
      {label}
      {control}
      {spec.help ? <p className="text-xs text-muted-foreground">{spec.help}</p> : null}
    </div>
  );
}

export function ActionFields({
  step,
  action,
  onChange,
  ctx,
}: {
  step: ActionStep;
  action: ActionSpec;
  onChange: (next: ActionStep) => void;
  ctx: FieldContext;
}) {
  if (!action.inputs.length) {
    return <p className="text-sm text-muted-foreground">This step has nothing to set up.</p>;
  }
  return (
    <div className="grid gap-4">
      {action.inputs.map((spec) => (
        <Field
          key={spec.key}
          spec={spec}
          step={step}
          ctx={ctx}
          set={(value) => onChange({ ...step, inputs: { ...step.inputs, [spec.key]: value } })}
        />
      ))}
    </div>
  );
}
