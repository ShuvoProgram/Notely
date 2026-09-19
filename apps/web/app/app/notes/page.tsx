import type { Metadata } from "next";

import { NotesEmptyState } from "@/features/notes/components/notes-workspace";

export const metadata: Metadata = { title: "Notes" };

export default function NotesIndexPage() {
  return <NotesEmptyState />;
}
