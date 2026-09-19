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
      <div className="w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm sm:p-8">{children}</div>
    </div>
  );
}
