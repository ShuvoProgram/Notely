import type { Metadata } from "next";
import { Suspense } from "react";

import { AIWorkspace } from "@/features/ai/components/ai-workspace";

export const metadata: Metadata = { title: "AI Assistant" };

export default function AIPage() {
  return (
    <Suspense>
      <AIWorkspace />
    </Suspense>
  );
}
