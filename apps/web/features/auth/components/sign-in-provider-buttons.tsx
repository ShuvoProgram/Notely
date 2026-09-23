"use client";

import { Button } from "@/components/ui/button";
import { useSignInProviders } from "@/features/auth/hooks";

/** Google's multi-colour "G", drawn inline so the button never waits on a network image. */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-[18px]" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.6-.4-3.9z" />
    </svg>
  );
}

/**
 * Renders a button per federated provider the backend has enabled. When none are configured
 * the component renders nothing, so the UI never advertises a sign-in method that can't work.
 */
export function SignInProviderButtons() {
  const { data: providers } = useSignInProviders();
  if (!providers || providers.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground">
        <span aria-hidden className="h-px flex-1 bg-border" />
        or continue with
        <span aria-hidden className="h-px flex-1 bg-border" />
      </div>
      <div className="grid gap-2">
        {providers.map((provider) => (
          <Button key={provider.id} type="button" variant="outline" className="h-11 w-full gap-2.5 rounded-xl text-[15px] font-bold" asChild>
            {/* A full navigation: the OAuth flow must leave the SPA and return via the callback. */}
            <a href={provider.start_url}>
              {provider.id === "google" ? <GoogleMark /> : null}
              Continue with {provider.display_name}
            </a>
          </Button>
        ))}
      </div>
    </div>
  );
}
