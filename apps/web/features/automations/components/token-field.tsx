"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import { tokenize, type DataOption, type DataSource } from "../lib";
import type { Catalog } from "../types";
import { DataPicker } from "./data-picker";

const CHIP =
  "mx-0.5 inline-flex max-w-full items-center rounded-md bg-ai-soft px-1.5 py-px align-baseline text-[12px] font-medium text-ai ring-1 ring-ai/25 select-none";

function chip(ref: string, label: string): HTMLSpanElement {
  const span = document.createElement("span");
  span.contentEditable = "false";
  span.dataset.ref = ref;
  span.className = CHIP;
  span.textContent = label;
  return span;
}

/** DOM → stored text: chips become `{{path}}`, line breaks become "\n". */
function serialise(root: HTMLElement): string {
  let out = "";
  const visit = (node: Node, first: boolean) => {
    if (node.nodeType === Node.TEXT_NODE) {
      out += (node.textContent ?? "").replace(/\u00a0/g, " ");
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.dataset.ref) {
      out += `{{${node.dataset.ref}}}`;
      return;
    }
    if (node.tagName === "BR") {
      out += "\n";
      return;
    }
    const block = node.tagName === "DIV" || node.tagName === "P";
    if (block && !first && !out.endsWith("\n")) out += "\n";
    node.childNodes.forEach((child, i) => visit(child, i === 0));
  };
  root.childNodes.forEach((child, i) => visit(child, i === 0));
  return out.replace(/\n$/, "");
}

/**
 * Text that can mix typed words with data from earlier steps. Data shows as a labelled chip
 * ("Gmail › Emails") — nobody has to see or type `{{…}}`.
 */
export function TokenField({
  id,
  value,
  onChange,
  labelFor,
  sources,
  catalog,
  multiline,
  placeholder,
  mappable = true,
  invalid,
  labelsVersion = "",
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  labelFor: (path: string) => string;
  sources: DataSource[];
  catalog?: Catalog;
  multiline?: boolean;
  placeholder?: string;
  mappable?: boolean;
  invalid?: boolean;
  /** Changes when chip labels can change (catalog loaded, a test revealed new fields). */
  labelsVersion?: string;
  "aria-label"?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const emitted = React.useRef<string | null>(null);
  const renderedVersion = React.useRef<string | null>(null);
  const range = React.useRef<Range | null>(null);
  const labels = React.useRef(labelFor);
  React.useEffect(() => {
    labels.current = labelFor;
  });

  // Render from the value only when it changed from outside (not while the user is typing).
  React.useEffect(() => {
    const el = ref.current;
    if (!el || (value === emitted.current && labelsVersion === renderedVersion.current)) return;
    const labelFor = labels.current;
    el.replaceChildren();
    for (const token of tokenize(value)) {
      if ("ref" in token) el.append(chip(token.ref, labelFor(token.ref)));
      else {
        token.text.split("\n").forEach((line, i) => {
          if (i > 0) el.append(document.createElement("br"));
          if (line) el.append(document.createTextNode(line));
        });
      }
    }
    emitted.current = value;
    renderedVersion.current = labelsVersion;
  }, [value, labelsVersion]);

  const emit = () => {
    const el = ref.current;
    if (!el) return;
    const next = serialise(el);
    emitted.current = next;
    onChange(next);
  };

  const remember = () => {
    const selection = window.getSelection();
    if (selection && selection.rangeCount && ref.current?.contains(selection.anchorNode)) {
      range.current = selection.getRangeAt(0).cloneRange();
    }
  };

  const insert = (option: DataOption) => {
    const el = ref.current;
    if (!el) return;
    const node = chip(option.path, labels.current(option.path));
    const space = document.createTextNode("\u00a0");
    const at = range.current && el.contains(range.current.startContainer) ? range.current : null;
    if (at) {
      at.deleteContents();
      at.insertNode(space);
      at.insertNode(node);
    } else {
      el.append(node, space);
    }
    const selection = window.getSelection();
    const after = document.createRange();
    after.setStartAfter(space);
    after.collapse(true);
    selection?.removeAllRanges();
    selection?.addRange(after);
    range.current = after.cloneRange();
    emit();
  };

  return (
    <div
      className={cn(
        "rounded-lg border border-input bg-background transition-shadow focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30 dark:bg-input/30",
        invalid && "border-destructive/60",
      )}
    >
      <div
        ref={ref}
        id={id}
        role="textbox"
        aria-multiline={multiline || undefined}
        aria-label={ariaLabel}
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={emit}
        onKeyUp={remember}
        onMouseUp={remember}
        onBlur={remember}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !multiline) e.preventDefault();
        }}
        onPaste={(e) => {
          e.preventDefault();
          const text = e.clipboardData.getData("text/plain");
          document.execCommand("insertText", false, multiline ? text : text.replace(/\n/g, " "));
        }}
        className={cn(
          "w-full break-words px-2.5 py-1.5 text-sm outline-none empty:before:pointer-events-none empty:before:text-muted-foreground empty:before:content-[attr(data-placeholder)]",
          multiline ? "min-h-20 whitespace-pre-wrap" : "min-h-8",
        )}
      />
      {mappable ? (
        <div className="flex items-center justify-end border-t border-glass-border px-1 py-0.5">
          <DataPicker sources={sources} catalog={catalog} onPick={insert} />
        </div>
      ) : null}
    </div>
  );
}
