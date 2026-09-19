import { Suspense } from "react";

import { NotesWorkspace } from "@/features/notes/components/notes-workspace";

export default function NotesLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <NotesWorkspace>{children}</NotesWorkspace>
    </Suspense>
  );
}
