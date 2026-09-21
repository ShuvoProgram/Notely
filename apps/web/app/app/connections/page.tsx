import { redirect } from "next/navigation";

// Connections live under Settings; old links keep working.
export default function LegacyConnectionsRedirect() {
  redirect("/app/settings/connections");
}
