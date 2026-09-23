import { AutomationEditor } from "@/features/automations/components/automation-builder";

export default async function AutomationPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { id } = await params;
  const { run } = await searchParams;
  return <AutomationEditor automationId={id} runId={run} />;
}
