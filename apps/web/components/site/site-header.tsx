import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

/** Public-site header (landing + legal pages). The app shell has its own navigation. */
export function SiteHeader() {
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-5 sm:px-6">
      <Link href="/" className="rounded-md focus-visible:outline-2" aria-label="Notely home">
        <Logo />
      </Link>
      <nav className="flex items-center gap-2" aria-label="Account">
        <Button variant="ghost" asChild>
          <Link href="/login">Sign in</Link>
        </Button>
        <Button asChild>
          <Link href="/signup">Get started</Link>
        </Button>
      </nav>
    </header>
  );
}
