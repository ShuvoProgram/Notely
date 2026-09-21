"use client";

import type { Editor } from "@tiptap/react";
import { useEditorState } from "@tiptap/react";
import {
  Bold,
  ChevronDown,
  Eraser,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link as LinkIcon,
  List,
  ListChecks,
  ListOrdered,
  type LucideIcon,
  MoreHorizontal,
  Pilcrow,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { NoteAIMenu } from "@/features/ai/components/note-ai-panel";
import type { NoteAIAction } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface ToolProps {
  icon: LucideIcon;
  label: string;
  shortcut?: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

function Tool({ icon: Icon, label, shortcut, active, disabled, onClick }: ToolProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          aria-pressed={active}
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()} // keep editor selection
          onClick={onClick}
          className={cn("rounded-md text-muted-foreground hover:text-foreground", active && "bg-accent text-foreground hover:bg-accent")}
        >
          <Icon aria-hidden />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {shortcut ? <span className="ml-2 opacity-60">{shortcut}</span> : null}
      </TooltipContent>
    </Tooltip>
  );
}

const BLOCKS: { id: "p" | 1 | 2 | 3; label: string; icon: LucideIcon }[] = [
  { id: "p", label: "Text", icon: Pilcrow },
  { id: 1, label: "Heading 1", icon: Heading1 },
  { id: 2, label: "Heading 2", icon: Heading2 },
  { id: 3, label: "Heading 3", icon: Heading3 },
];

/**
 * Compact formatting bar: the things people reach for every minute are one click away, the
 * rest sit in a small overflow. It is contextual — the block menu and the marks reflect the
 * caret — but it stays put so it never covers the text.
 */
export function EditorToolbar({ editor, onAskAI }: { editor: Editor; onAskAI?: (action: NoteAIAction) => void }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      strike: e.isActive("strike"),
      heading: e.isActive("heading", { level: 1 }) ? 1 : e.isActive("heading", { level: 2 }) ? 2 : e.isActive("heading", { level: 3 }) ? 3 : ("p" as const),
      bullet: e.isActive("bulletList"),
      ordered: e.isActive("orderedList"),
      task: e.isActive("taskList"),
      quote: e.isActive("blockquote"),
      link: e.isActive("link"),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
      linkHref: (e.getAttributes("link").href as string | undefined) ?? "",
    }),
  });

  const [linkOpen, setLinkOpen] = React.useState(false);
  const [linkValue, setLinkValue] = React.useState("");

  const applyLink = () => {
    const href = linkValue.trim();
    if (!href) editor.chain().focus().extendMarkRange("link").unsetLink().run();
    else editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    setLinkOpen(false);
  };

  const block = BLOCKS.find((b) => b.id === state.heading) ?? { id: "p" as const, label: "Text", icon: Pilcrow };
  const keep = (e: React.MouseEvent) => e.preventDefault();

  return (
    <div role="toolbar" aria-label="Formatting" className="sticky top-0 z-20 -mx-1 mb-6 flex items-center gap-0.5 overflow-x-auto rounded-lg border border-glass-border bg-background/85 px-1 py-1 backdrop-blur-md [scrollbar-width:none]">
      <Tool icon={Undo2} label="Undo" shortcut="⌘Z" disabled={!state.canUndo} onClick={() => editor.chain().focus().undo().run()} />
      <Tool icon={Redo2} label="Redo" shortcut="⌘⇧Z" disabled={!state.canRedo} onClick={() => editor.chain().focus().redo().run()} />
      <Separator orientation="vertical" className="mx-1 h-4" />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="sm" aria-label={`Block: ${block.label}`} onMouseDown={keep} className="h-7 gap-1 rounded-md px-2 text-xs font-medium text-muted-foreground hover:text-foreground">
            <block.icon aria-hidden className="size-3.5" />
            <span className="hidden sm:inline">{block.label}</span>
            <ChevronDown className="size-3 opacity-60" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-44" onCloseAutoFocus={(e) => e.preventDefault()}>
          {BLOCKS.map((b) => (
            <DropdownMenuCheckboxItem
              key={String(b.id)}
              checked={state.heading === b.id}
              onSelect={() => (b.id === "p" ? editor.chain().focus().setParagraph().run() : editor.chain().focus().toggleHeading({ level: b.id }).run())}
            >
              <b.icon aria-hidden className="mr-2 size-4 text-muted-foreground" /> {b.label}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Separator orientation="vertical" className="mx-1 h-4" />

      <Tool icon={Bold} label="Bold" shortcut="⌘B" active={state.bold} onClick={() => editor.chain().focus().toggleBold().run()} />
      <Tool icon={Italic} label="Italic" shortcut="⌘I" active={state.italic} onClick={() => editor.chain().focus().toggleItalic().run()} />
      <Tool icon={Strikethrough} label="Strikethrough" shortcut="⌘⇧S" active={state.strike} onClick={() => editor.chain().focus().toggleStrike().run()} />
      <Popover
        open={linkOpen}
        onOpenChange={(open) => {
          setLinkOpen(open);
          if (open) setLinkValue(state.linkHref);
        }}
      >
        <PopoverTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Link" aria-pressed={state.link} onMouseDown={keep} className={cn("rounded-md text-muted-foreground hover:text-foreground", state.link && "bg-accent text-foreground")}>
            <LinkIcon aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-2" align="start">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              applyLink();
            }}
          >
            <Input aria-label="Link URL" placeholder="https://" value={linkValue} onChange={(e) => setLinkValue(e.target.value)} autoFocus />
            <Button type="submit" size="sm">
              {linkValue.trim() ? "Set" : "Remove"}
            </Button>
          </form>
        </PopoverContent>
      </Popover>
      <Separator orientation="vertical" className="mx-1 h-4" />

      <Tool icon={List} label="Bullet list" shortcut="⌘⇧8" active={state.bullet} onClick={() => editor.chain().focus().toggleBulletList().run()} />
      <Tool icon={ListOrdered} label="Numbered list" shortcut="⌘⇧7" active={state.ordered} onClick={() => editor.chain().focus().toggleOrderedList().run()} />
      <Tool icon={ListChecks} label="Checklist" shortcut="⌘⇧9" active={state.task} onClick={() => editor.chain().focus().toggleTaskList().run()} />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="More formatting" onMouseDown={keep} className={cn("rounded-md text-muted-foreground hover:text-foreground", state.quote && "bg-accent text-foreground")}>
            <MoreHorizontal aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-52" onCloseAutoFocus={(e) => e.preventDefault()}>
          <DropdownMenuCheckboxItem checked={state.quote} onSelect={() => editor.chain().focus().toggleBlockquote().run()}>
            <Quote aria-hidden className="mr-2 size-4 text-muted-foreground" /> Quote
          </DropdownMenuCheckboxItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}>
            <Eraser aria-hidden className="mr-2 size-4 text-muted-foreground" /> Clear formatting
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {onAskAI ? (
        <span className="ml-auto pl-2" onMouseDown={keep}>
          <NoteAIMenu onPick={onAskAI} />
        </span>
      ) : null}
    </div>
  );
}
