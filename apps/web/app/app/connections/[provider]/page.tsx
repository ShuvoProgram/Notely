import { redirect } from "next/navigation";

export default async function LegacyProviderRedirect({ params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  redirect(`/app/settings/connections/${provider}`);
}
