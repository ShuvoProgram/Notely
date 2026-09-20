import { redirect } from "next/navigation";

// Connections graduated to a top-level area; old links keep working.
export default function LegacyConnectionsRedirect() {
  redirect("/app/connections");
}
