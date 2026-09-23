import Link from "next/link";
import { redirect } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { AuthShowcase } from "@/features/auth/components/auth-showcase";
import { getCurrentUser } from "@/lib/api/server";

import "./auth.css";

/*
 * Sign in / sign up: the form owns the left half (the whole screen on phones and tablets), a quiet
 * brand panel fills the right on large screens. The form column is a plain flex column so the
 * on-screen keyboard can never push the submit button out of reach.
 */
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (user) redirect("/app");

  return (
    <div className="grid flex-1 bg-background lg:grid-cols-2">
      <div className="flex min-h-svh flex-col px-5 sm:px-8">
        <header className="flex h-16 shrink-0 items-center justify-between">
          <Link href="/" className="rounded-md focus-visible:outline-2" aria-label="Notely home">
            <Logo />
          </Link>
          <ThemeToggle />
        </header>
        <main className="flex flex-1 items-start justify-center pb-10 pt-6 sm:items-center sm:pt-0">
          <div className="animate-fade-up w-full max-w-[400px]">{children}</div>
        </main>
        <footer className="flex h-14 shrink-0 items-center justify-center">
          <nav aria-label="Legal" className="flex gap-5 text-xs text-muted-foreground">
            <Link href="/privacy-policy" className="underline-offset-4 hover:text-foreground hover:underline">
              Privacy Policy
            </Link>
            <Link href="/terms-and-conditions" className="underline-offset-4 hover:text-foreground hover:underline">
              Terms &amp; Conditions
            </Link>
          </nav>
        </footer>
      </div>
      <AuthShowcase />
    </div>
  );
}
