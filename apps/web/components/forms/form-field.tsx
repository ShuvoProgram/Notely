import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FormFieldProps extends React.ComponentProps<typeof Input> {
  label: string;
  error?: string;
  hint?: string;
}

/** Accessible label + input + error trio. Errors are announced via aria-describedby. */
export function FormField({ label, error, hint, id, className, ...props }: FormFieldProps) {
  const generatedId = React.useId();
  const inputId = id ?? generatedId;
  const describedBy = [error ? `${inputId}-error` : null, hint ? `${inputId}-hint` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={inputId}>{label}</Label>
      <Input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...props}
      />
      {hint && !error ? (
        <p id={`${inputId}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${inputId}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
