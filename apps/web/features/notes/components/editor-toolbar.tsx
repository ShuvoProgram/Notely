"use client";

import type { Editor } from "@tiptap/react";
import { useEditorState } from "@tiptap/react";
import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Italic,
  Link as LinkIcon,
  List,
  ListChecks,
  ListOrdered,
  type LucideIcon,
  Quote,
  Redo2,
  SquareCode,
  Strikethrough,
  Undo2,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
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
          className={cn("rounded-lg", active && "bg-ai-soft text-ai hover:bg-ai-soft hover:text-ai")}
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

export function EditorToolbar({ editor, onAskAI }: { editor: Editor; onAskAI?: (action: NoteAIAction) => void }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      strike: e.isActive("strike"),
      code: e.isActive("code"),
      h1: e.isActive("heading", { level: 1 }),
      h2: e.isActive("heading", { level: 2 }),
      bullet: e.isActive("bulletList"),
      ordered: e.isActive("orderedList"),
      task: e.isActive("taskList"),
      quote: e.isActive("blockquote"),
      codeBlock: e.isActive("codeBlock"),
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
    if (!href) {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
    } else {
      editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    }
    setLinkOpen(false);
  };

  return (
    <div
      role="toolbar"
      aria-label="Formatting"
      className="glass-2 sticky top-2 z-20 mb-6 flex flex-wrap items-center gap-0.5 rounded-xl p-1"
    >
      <Tool icon={Undo2} label="Undo" shortcut="⌘Z" disabled={!state.canUndo} onClick={() => editor.chain().focus().undo().run()} />
      <Tool icon={Redo2} label="Redo" shortcut="⌘⇧Z" disabled={!state.canRedo} onClick={() => editor.chain().focus().redo().run()} />
      <Separator orientation="vertical" className="mx-1 h-5" />
      <Tool icon={Heading1} label="Heading 1" active={state.h1} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} />
      <Tool icon={Heading2} label="Heading 2" active={state.h2} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} />
      <Separator orientation="vertical" className="mx-1 h-5" />
      <Tool icon={Bold} label="Bold" shortcut="⌘B" active={state.bold} onClick={() => editor.chain().focus().toggleBold().run()} />
      <Tool icon={Italic} label="Italic" shortcut="⌘I" active={state.italic} onClick={() => editor.chain().focus().toggleItalic().run()} />
      <Tool icon={Strikethrough} label="Strikethrough" active={state.strike} onClick={() => editor.chain().focus().toggleStrike().run()} />
      <Tool icon={Code} label="Inline code" shortcut="⌘E" active={state.code} onClick={() => editor.chain().focus().toggleCode().run()} />
      <Popover
        open={linkOpen}
        onOpenChange={(open) => {
          setLinkOpen(open);
          if (open) setLinkValue(state.linkHref);
        }}
      >
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Link"
            aria-pressed={state.link}
            onMouseDown={(e) => e.preventDefault()}
            className={cn(state.link && "bg-accent text-accent-foreground")}
          >
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
            <Input
              aria-label="Link URL"
              placeholder="https://"
              value={linkValue}
              onChange={(e) => setLinkValue(e.target.value)}
              autoFocus
            />
            <Button type="submit" size="sm">
              {linkValue.trim() ? "Set" : "Remove"}
            </Button>
          </form>
        </PopoverContent>
      </Popover>
      <Separator orientation="vertical" className="mx-1 h-5" />
      <Tool icon={List} label="Bullet list" active={state.bullet} onClick={() => editor.chain().focus().toggleBulletList().run()} />
      <Tool icon={ListOrdered} label="Numbered list" active={state.ordered} onClick={() => editor.chain().focus().toggleOrderedList().run()} />
      <Tool icon={ListChecks} label="Task list" active={state.task} onClick={() => editor.chain().focus().toggleTaskList().run()} />
      <Tool icon={Quote} label="Quote" active={state.quote} onClick={() => editor.chain().focus().toggleBlockquote().run()} />
      <Tool icon={SquareCode} label="Code block" active={state.codeBlock} onClick={() => editor.chain().focus().toggleCodeBlock().run()} />
      {onAskAI ? (
        <span className="ml-auto" onMouseDown={(e) => e.preventDefault()}>
          <NoteAIMenu onPick={onAskAI} />
        </span>
      ) : null}
    </div>
  );
}
