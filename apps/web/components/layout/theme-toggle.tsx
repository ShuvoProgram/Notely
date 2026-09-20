"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // next-themes resolves the theme only on the client; before hydration assume dark (the default).
  const mounted = React.useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const dark = !mounted || resolvedTheme !== "light";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          onClick={() => setTheme(dark ? "light" : "dark")}
        >
          {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{dark ? "Light theme" : "Dark theme"}</TooltipContent>
    </Tooltip>
  );
}
