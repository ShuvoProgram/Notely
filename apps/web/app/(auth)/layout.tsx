import Link from "next/link";
import { redirect } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { getCurrentUser } from "@/lib/api/server";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (user) redirect("/app");

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-10 sm:justify-center">
      <Link href="/" className="mb-8 rounded-md focus-visible:outline-2">
        <Logo />
      </Link>
      <div className="glass-2 animate-fade-up w-full max-w-sm rounded-2xl p-6 sm:p-8">{children}</div>
      <nav aria-label="Legal" className="mt-6 flex gap-4 text-xs text-muted-foreground">
        <Link href="/privacy-policy" className="underline-offset-4 hover:text-foreground hover:underline">
          Privacy Policy
        </Link>
        <Link href="/terms-and-conditions" className="underline-offset-4 hover:text-foreground hover:underline">
          Terms &amp; Conditions
        </Link>
      </nav>
    </div>
  );
}
