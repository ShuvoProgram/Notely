import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { InviteAccept } from "@/features/notes/components/invite-accept";
import { getCurrentUser } from "@/lib/api/server";

export const metadata: Metadata = { title: "Shared note" };

/** Landing page for the link in an invitation email. Works signed in or out. */
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const user = await getCurrentUser();
  return (
    <div className="flex flex-1 flex-col items-center px-4 py-10 sm:justify-center">
      <Link href="/" className="mb-8 rounded-md focus-visible:outline-2">
        <Logo />
      </Link>
      <div className="glass-2 animate-fade-up w-full max-w-md rounded-2xl p-6 sm:p-8">
        <InviteAccept token={token} user={user} />
      </div>
    </div>
  );
}
