import type { Metadata } from "next";

import { NoteEditor } from "@/features/notes/components/note-editor";

export const metadata: Metadata = { title: "Note" };

export default async function NotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <NoteEditor noteId={id} />;
}
