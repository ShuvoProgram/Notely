import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser } from "@/lib/api/server";

export const metadata: Metadata = { title: "Home" };

export default async function AppHomePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const firstName = user.display_name.split(/\s+/)[0] ?? user.display_name;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Good to see you, {firstName}.</h1>
        <p className="mt-1 text-muted-foreground">
          Your workspace is ready. Notes, search and the AI assistant arrive in the next release.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>Signed in as {user.email}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild>
              <Link href="/app/settings/profile">Edit profile</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Security</CardTitle>
            <CardDescription>Review active sessions and change your password.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild>
              <Link href="/app/settings/security">Manage security</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
