"use client";

import { Button } from "@/components/ui/button";
import { useSignInProviders } from "@/features/auth/hooks";

/**
 * Renders a button per federated provider the backend has enabled. When none are configured
 * the component renders nothing, so the UI never advertises a sign-in method that can't work.
 */
export function SignInProviderButtons() {
  const { data: providers } = useSignInProviders();
  if (!providers || providers.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
        <span className="h-px flex-1 bg-border" />
        or
        <span className="h-px flex-1 bg-border" />
      </div>
      <div className="grid gap-2">
        {providers.map((provider) => (
          <Button key={provider.id} type="button" variant="outline" className="w-full" asChild>
            {/* A full navigation: the OAuth flow must leave the SPA and return via the callback. */}
            <a href={provider.start_url}>Continue with {provider.display_name}</a>
          </Button>
        ))}
      </div>
    </div>
  );
}
