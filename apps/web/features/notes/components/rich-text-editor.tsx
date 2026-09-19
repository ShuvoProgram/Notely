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
import type { TipTapDoc } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface RichTextEditorProps {
  /** Initial document. Changing `documentKey` re-initialises the editor with new content. */
  content: TipTapDoc;
  documentKey: string;
  editable?: boolean;
  placeholder?: string;
  onChange?: (doc: TipTapDoc) => void;
  onReady?: (editor: Editor) => void;
  className?: string;
}

export function RichTextEditor({
  content,
  documentKey,
  editable = true,
  placeholder = "Start writing, or press / for commands…",
  onChange,
  onReady,
  className,
}: RichTextEditorProps) {
  const onChangeRef = React.useRef(onChange);
  React.useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

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
      onUpdate: ({ editor: e }) => {
        onChangeRef.current?.(e.getJSON() as TipTapDoc);
      },
      onCreate: ({ editor: e }) => onReady?.(e),
    },
    [documentKey],
  );

  React.useEffect(() => {
    editor?.setEditable(editable);
  }, [editor, editable]);

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      {editor && editable ? <EditorToolbar editor={editor} /> : null}
      <EditorContent editor={editor} className="flex-1" />
      {editor ? (
        <p className="mt-6 text-xs text-muted-foreground" aria-live="polite">
          {editor.storage.characterCount.words()} words
        </p>
      ) : null}
    </div>
  );
}
