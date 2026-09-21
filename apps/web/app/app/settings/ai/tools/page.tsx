import type { Metadata } from "next";

import { ToolsDirectory } from "@/features/ai/components/tools-directory";

export const metadata: Metadata = { title: "What the assistant can do" };

export default function AssistantToolsPage() {
  return <ToolsDirectory />;
}
