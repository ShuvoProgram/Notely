"use client";

import * as React from "react";

import { AlertCircle, Check, Circle, Eye, EyeOff } from "@/components/icons";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PASSWORD_MIN } from "@/features/auth/schemas";
import { cn } from "@/lib/utils";

type InputProps = React.ComponentProps<typeof Input>;

interface AuthFieldProps extends InputProps {
  label: string;
  error?: string;
  hint?: React.ReactNode;
  /** The value has been checked and is fine: a quiet check mark, never colour alone. */
  valid?: boolean;
  /** Extra line under the error (e.g. "Sign in instead"). */
  errorAction?: React.ReactNode;
  /** Rendered inside the input's right edge (used by PasswordField for the toggle). */
  trailing?: React.ReactNode;
  /** Rendered under the input, above hint/error (password requirements). */
  below?: React.ReactNode;
}

/**
 * Label + input + feedback for the auth forms: a taller, touch-friendly input, errors with an icon
 * and text (announced through aria-describedby), and an optional valid state.
 */
export function AuthField({ label, error, hint, valid, errorAction, trailing, below, id, className, ...props }: AuthFieldProps) {
  const generated = React.useId();
  const inputId = id ?? generated;
  const describedBy = [error ? `${inputId}-error` : null, hint && !error ? `${inputId}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </Label>
      <div className="relative">
        <Input
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn("h-11 rounded-xl px-3.5 text-base md:text-[15px]", (trailing || valid) && "pr-11")}
          {...props}
        />
        {trailing ? (
          <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>
        ) : valid && !error ? (
          <span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center text-ai">
            <Check className="size-4" aria-hidden />
            <span className="sr-only">Looks good</span>
          </span>
        ) : null}
      </div>
      {below}
      {error ? (
        <div id={`${inputId}-error`} aria-live="polite" className="space-y-1">
          <p className="flex items-start gap-1.5 text-[13px] font-medium text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {error}
          </p>
          {errorAction}
        </div>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-[13px] text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

interface PasswordFieldProps extends Omit<AuthFieldProps, "type" | "trailing"> {
  /** Show the live requirement checklist and strength meter (sign-up). */
  requirements?: boolean;
}

/** A password input with show/hide, a Caps Lock warning and (optionally) live requirements. */
export function PasswordField({ requirements, onKeyUp, onBlur, onChange, hint, ...props }: PasswordFieldProps) {
  const [visible, setVisible] = React.useState(false);
  const [caps, setCaps] = React.useState(false);
  const [value, setValue] = React.useState("");
  const id = React.useId();
  const inputId = props.id ?? id;

  const capsHint = caps ? (
    <span className="flex items-center gap-1.5 font-medium text-warning">
      <AlertCircle className="size-3.5" aria-hidden /> Caps Lock is on
    </span>
  ) : null;

  return (
    <AuthField
      {...props}
      id={inputId}
      type={visible ? "text" : "password"}
      // Browsers shouldn't try to "fix" a password while it's visible.
      autoCapitalize="none"
      autoCorrect="off"
      spellCheck={false}
      hint={capsHint ?? hint}
      onKeyUp={(e) => {
        setCaps(e.getModifierState("CapsLock"));
        onKeyUp?.(e);
      }}
      onBlur={(e) => {
        setCaps(false);
        onBlur?.(e);
      }}
      onChange={(e) => {
        setValue(e.target.value);
        onChange?.(e);
      }}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          aria-controls={inputId}
          className="grid size-9 cursor-pointer place-items-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          {visible ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        </button>
      }
      below={requirements ? <PasswordChecklist value={value} /> : undefined}
    />
  );
}

/** The rules the server enforces, checked as you type, plus a rough strength reading. */
function PasswordChecklist({ value }: { value: string }) {
  const rules = [
    { label: `At least ${PASSWORD_MIN} characters`, met: value.length >= PASSWORD_MIN },
    { label: "No spaces at the start or end", met: value.length > 0 && value.trim() === value },
  ];
  const strength = scorePassword(value);
  return (
    <div className="space-y-2 pt-1">
      {value ? (
        <div className="flex items-center gap-2.5" aria-live="polite">
          <div className="grid flex-1 grid-cols-4 gap-1" aria-hidden>
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={cn("h-1 rounded-full transition-colors duration-300", i <= strength.level ? strength.bar : "bg-foreground/10")} />
            ))}
          </div>
          <span className="w-24 text-right text-xs font-medium text-muted-foreground">Strength: {strength.label}</span>
        </div>
      ) : null}
      <ul className="space-y-1">
        {rules.map((r) => (
          <li key={r.label} className={cn("flex items-center gap-1.5 text-[13px] transition-colors", r.met ? "text-foreground" : "text-muted-foreground")}>
            {r.met ? <Check className="size-3.5 text-ai" aria-hidden /> : <Circle className="size-3.5" aria-hidden />}
            {r.label}
            <span className="sr-only">{r.met ? "(met)" : "(not met yet)"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A deliberately simple estimate: length does most of the work, variety adds a little. */
function scorePassword(v: string): { level: number; label: string; bar: string } {
  if (!v) return { level: 0, label: "", bar: "" };
  let score = 0;
  if (v.length >= PASSWORD_MIN) score++;
  if (v.length >= 14) score++;
  if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++;
  if (/[\d\W_]/.test(v)) score++;
  if (v.trim().split(/\s+/).length >= 3) score++; // a short sentence is a strong password
  if (v.length < PASSWORD_MIN) score = Math.min(score, 1);
  const level = Math.max(1, Math.min(4, score));
  return [
    { level, label: "Weak", bar: "bg-destructive" },
    { level, label: "Fair", bar: "bg-warning" },
    { level, label: "Good", bar: "bg-ai" },
    { level, label: "Strong", bar: "bg-ai" },
  ][level - 1]!;
}
