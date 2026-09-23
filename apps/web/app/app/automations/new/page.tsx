import { AutomationEditor } from "@/features/automations/components/automation-builder";

export default async function NewAutomationPage({ searchParams }: { searchParams: Promise<{ template?: string; draft?: string }> }) {
  const { template, draft } = await searchParams;
  return <AutomationEditor templateId={template} fromAIDraft={draft === "1"} />;
}
