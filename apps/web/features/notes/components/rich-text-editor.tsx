"use client";

import CharacterCount from "@tiptap/extension-character-count";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import Typography from "@tiptap/extension-typography";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import * as React from "react";

import { EditorToolbar } from "@/features/notes/components/editor-toolbar";
import { ListItemMove } from "@/features/notes/extensions/list-item-move";
import { SelectionAIMenu } from "@/features/notes/components/selection-ai-menu";
import type { NoteAIAction, TipTapDoc } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface RichTextEditorProps {
  /** Initial document. Changing `documentKey` re-initialises the editor with new content. */
  content: TipTapDoc;
  documentKey: string;
  editable?: boolean;
  placeholder?: string;
  onChange?: (doc: TipTapDoc) => void;
  onReady?: (editor: Editor) => void;
  /** Hands a chosen AI action (from the toolbar or the selection menu) to the suggestion panel. */
  onAskAI?: (action: NoteAIAction) => void;
  className?: string;
}

export function RichTextEditor({
  content,
  documentKey,
  editable = true,
  placeholder = "Start writing, or select text and ask AI…",
  onChange,
  onReady,
  onAskAI,
  className,
}: RichTextEditorProps) {
  const onChangeRef = React.useRef(onChange);
  React.useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  const editor = useEditor(
    {
      immediatelyRender: false,
      editable,
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3] },
          link: false,
        }),
        Link.configure({
          openOnClick: false,
          autolink: true,
          defaultProtocol: "https",
          HTMLAttributes: { rel: "noopener noreferrer nofollow", target: "_blank" },
        }),
        TaskList,
        TaskItem.configure({ nested: true }),
        Typography,
        CharacterCount,
        ListItemMove,
        Placeholder.configure({ placeholder }),
      ],
      content,
      editorProps: {
        attributes: {
          class: "notely-editor focus:outline-none",
          "aria-label": "Note body",
          role: "textbox",
          "aria-multiline": "true",
        },
      },
      onUpdate: ({ editor: e, transaction }) => {
        // `setEditable()` and other non-document transactions also emit `update`; only a
        // transaction that changed the document is an edit. Otherwise every open would
        // autosave the untouched body and the note would jump to the top of the list.
        if (!transaction.docChanged) return;
        onChangeRef.current?.(e.getJSON() as TipTapDoc);
      },
      onCreate: ({ editor: e }) => onReady?.(e),
    },
    [documentKey],
  );

  React.useEffect(() => {
    if (editor && editor.isEditable !== editable) editor.setEditable(editable, false);
  }, [editor, editable]);

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      {editor && editable ? <EditorToolbar editor={editor} onAskAI={onAskAI} /> : null}
      <div ref={containerRef} className="relative flex-1">
        {editor && editable && onAskAI ? <SelectionAIMenu editor={editor} containerRef={containerRef} onPick={onAskAI} /> : null}
        <EditorContent editor={editor} />
      </div>
      {editor ? (
        <p className="mt-8 text-xs text-muted-foreground" aria-live="polite">
          {editor.storage.characterCount.words()} words · {editor.storage.characterCount.characters()} characters
        </p>
      ) : null}
    </div>
  );
}
