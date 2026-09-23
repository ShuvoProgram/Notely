"use client";

import { ChevronDown, Plus, X } from "@/components/icons";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { OPERATORS, isUnary, type DataSource } from "../lib";
import type { Catalog, Condition, ConditionRule, Operator } from "../types";
import { DataPicker } from "./data-picker";
import { TokenField } from "./token-field";

/**
 * "Only continue if [Number of emails] [is more than] [5]". Each rule compares a piece of data
 * with a value; several rules combine with "all of these" or "any of these".
 */
export function ConditionEditor({
  value,
  onChange,
  sources,
  catalog,
  labelFor,
  labelsVersion,
  idPrefix,
}: {
  value: Condition;
  onChange: (next: Condition) => void;
  sources: DataSource[];
  catalog?: Catalog;
  labelFor: (path: string) => string;
  labelsVersion: string;
  idPrefix: string;
}) {
  const rules = value.rules.filter((r): r is ConditionRule => "operator" in r);
  const setRule = (index: number, next: ConditionRule) =>
    onChange({ ...value, rules: rules.map((r, i) => (i === index ? next : r)) });

  return (
    <div className="space-y-2">
      {rules.length > 1 ? (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Continue when</span>
          <Select value={value.match} onValueChange={(match) => onChange({ ...value, match: match as Condition["match"] })}>
            <SelectTrigger size="sm" className="w-auto" aria-label="Match">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">all of these are true</SelectItem>
              <SelectItem value="any">any of these is true</SelectItem>
            </SelectContent>
          </Select>
        </div>
      ) : null}
      {rules.map((rule, index) => {
        const leftRef = /^\{\{\s*(.+?)\s*\}\}$/.exec(rule.left)?.[1];
        return (
          <div key={index} className="space-y-2 rounded-xl border border-glass-border bg-muted/20 p-2.5">
            <div className="flex items-start gap-2">
              <DataPicker
                sources={sources}
                catalog={catalog}
                onPick={(option) => setRule(index, { ...rule, left: `{{${option.path}}}` })}
                trigger={
                  <Button type="button" variant="outline" className="h-auto min-h-8 flex-1 justify-between gap-2 whitespace-normal py-1.5 text-left" aria-label={`Information to check ${index + 1}`}>
                    <span className={leftRef ? "text-ai" : "text-muted-foreground"}>{leftRef ? labelFor(leftRef) : "Choose information…"}</span>
                    <ChevronDown className="size-4 shrink-0 opacity-60" aria-hidden />
                  </Button>
                }
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove condition ${index + 1}`}
                disabled={rules.length === 1}
                onClick={() => onChange({ ...value, rules: rules.filter((_, i) => i !== index) })}
              >
                <X className="size-4" />
              </Button>
            </div>
            <div className="grid gap-2 sm:grid-cols-[11rem_minmax(0,1fr)] sm:items-start">
              <Select
                value={rule.operator}
                onValueChange={(operator) =>
                  setRule(index, { ...rule, operator: operator as Operator, right: isUnary(operator as Operator) ? null : rule.right ?? "" })
                }
              >
                <SelectTrigger className="w-full" aria-label={`Comparison ${index + 1}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OPERATORS.map((op) => (
                    <SelectItem key={op.value} value={op.value}>
                      {op.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {isUnary(rule.operator) ? null : (
                <TokenField
                  id={`${idPrefix}-right-${index}`}
                  aria-label={`Compare with ${index + 1}`}
                  value={String(rule.right ?? "")}
                  onChange={(right) => setRule(index, { ...rule, right })}
                  labelFor={labelFor}
                  labelsVersion={labelsVersion}
                  sources={sources}
                  catalog={catalog}
                  placeholder="A value, e.g. 5"
                />
              )}
            </div>
          </div>
        );
      })}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => onChange({ ...value, rules: [...rules, { left: "", operator: "is_not_empty" }] })}
      >
        <Plus className="size-4" aria-hidden /> Add another condition
      </Button>
    </div>
  );
}
