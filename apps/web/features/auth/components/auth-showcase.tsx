import { CalendarDays, Check, NotebookPen, Sparkles, type IconComponent } from "@/components/icons";

const STEPS: { icon: IconComponent; label: string; title: string; detail: string }[] = [
  { icon: NotebookPen, label: "Note", title: "Q3 launch plan", detail: "Launch timeline · Product updates" },
  { icon: Sparkles, label: "Assistant", title: "Create 2 tasks from this note?", detail: "Approved" },
  { icon: Check, label: "Task", title: "Send pricing proposal", detail: "High · Today · 3:30 PM" },
  { icon: CalendarDays, label: "Google Calendar", title: "Pricing proposal", detail: "Today · 3:30 – 4:00 PM" },
];

// Only things the product enforces today.
const TRUST = ["You approve every change the assistant makes", "App connections are encrypted at rest", "Two-factor sign-in when you want it"];

/**
 * The quiet half of the auth screen (lg+ only): what Notely does, in the same note → assistant →
 * task → calendar story as the landing page. A soft highlight walks down the steps with CSS only
 * (no JS, nothing to run on small screens); it stops entirely under reduced motion.
 */
export function AuthShowcase() {
  return (
    <aside aria-label="About Notely" className="relative m-3 hidden overflow-hidden rounded-[28px] bg-foreground/[0.035] ring-1 ring-foreground/10 lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-14">
      <div aria-hidden className="auth-dots pointer-events-none absolute inset-0" />
      <div className="relative max-w-md">
        <p className="text-sm font-bold text-ai">How Notely works</p>
        <p className="mt-3 text-4xl font-black leading-[1.02] tracking-[-0.04em] xl:text-5xl">Think it. Ask it. Notely does the rest.</p>
        <p className="mt-4 text-[15px] leading-relaxed text-foreground-secondary">Your notes become tasks on your calendar, and nothing changes without your go-ahead.</p>
      </div>

      <ol aria-label="From a note to your calendar" className="relative my-8 max-w-md space-y-3">
        {STEPS.map((s, i) => (
          <li key={s.label} className="auth-step relative flex items-center gap-3.5 rounded-2xl bg-card p-3.5" style={{ animationDelay: i ? `${2 * i - 8}s` : undefined }}>
            {i < STEPS.length - 1 ? <span aria-hidden className="absolute -bottom-3 left-[1.9rem] h-3 w-px bg-foreground/15" /> : null}
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-foreground/[0.06]">
              <s.icon className="size-4" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">{s.label}</span>
              <span className="block truncate text-sm font-bold">{s.title}</span>
              <span className="block truncate text-xs text-muted-foreground">{s.detail}</span>
            </span>
          </li>
        ))}
      </ol>

      <ul className="relative space-y-2 text-sm text-foreground-secondary [@media(max-height:760px)]:hidden">
        {TRUST.map((t) => (
          <li key={t} className="flex items-center gap-2">
            <Check className="size-4 text-ai" aria-hidden />
            {t}
          </li>
        ))}
      </ul>
    </aside>
  );
}
