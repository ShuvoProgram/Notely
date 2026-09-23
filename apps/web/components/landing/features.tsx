import { Bell, CalendarDays, Folder, KeyRound, ListChecks, NotebookPen, Palette, Sparkles, Star, Tag, Users, Workflow, type IconComponent } from "@/components/icons";
import { SectionLabel, Words } from "@/components/landing/reveal";
import { cn } from "@/lib/utils";

interface Feature {
  icon: IconComponent;
  title: string;
  body: string;
  points: { icon: IconComponent; label: string }[];
  wide?: boolean;
  full?: boolean;
}

// Only shipped capabilities. Wording mirrors what each screen in the app actually offers.
const FEATURES: Feature[] = [
  {
    icon: NotebookPen,
    title: "Notes",
    body: "A rich editor with folders, tags and favourites, reminders, version history, and sharing with the people you work with.",
    points: [
      { icon: Folder, label: "Folders" },
      { icon: Tag, label: "Tags" },
      { icon: Star, label: "Favourites" },
      { icon: Users, label: "Sharing" },
    ],
    wide: true,
  },
  {
    icon: Sparkles,
    title: "AI assistant",
    body: "Searches your notes, tasks and connected apps, plans multi-step work, and asks before every change. Use the built-in model or bring your own key.",
    points: [{ icon: KeyRound, label: "Approval per change" }],
  },
  {
    icon: ListChecks,
    title: "Tasks",
    body: "Dates, times and priorities, sections by due date, bulk actions, and sync to Google Calendar.",
    points: [{ icon: CalendarDays, label: "Calendar sync" }],
  },
  {
    icon: Workflow,
    title: "Automations",
    body: "Run work on a schedule or when something happens. Describe it to the assistant or build it step by step, then test it safely first.",
    points: [],
  },
  {
    icon: Bell,
    title: "Reminders & inbox",
    body: "Reminders for notes and tasks, and one quiet inbox for due dates, automation runs and connection updates.",
    points: [],
  },
  {
    icon: Palette,
    title: "Yours to shape",
    body: "Light or dark, five backdrops and adjustable glass, saved to your account on every device.",
    points: [],
    full: true,
  },
];

export function Features() {
  return (
    <section id="features" aria-labelledby="features-heading" className="scroll-mt-20 border-t border-foreground/10">
      <div className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 lg:py-28">
        <SectionLabel index="02">Features</SectionLabel>
        <div className="mt-5 grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <h2 id="features-heading" data-reveal="words" className="text-[clamp(2.25rem,5.5vw,4rem)] font-black leading-[0.98] tracking-[-0.04em]">
            <Words text="One workspace. No tab juggling." />
          </h2>
          <p data-reveal className="max-w-md text-base leading-relaxed text-foreground-secondary sm:text-lg">
            The places you write, plan and follow up live together, so the assistant can see the whole picture.
          </p>
        </div>

        {/* A ruled grid: 1px gaps over a tinted background read as hairlines between cells. */}
        <ul className="mt-14 grid gap-px border border-foreground/15 bg-foreground/15 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <li key={f.title} data-reveal className={cn("landing-feature group relative flex flex-col bg-background p-6 sm:p-7", f.wide && "lg:col-span-2", f.full && "lg:col-span-3")}>
              <span aria-hidden className="absolute inset-x-0 top-0 h-[3px] origin-left scale-x-0 bg-ai transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-x-100" />
              <div className="flex items-start justify-between">
                <span className="grid size-11 place-items-center rounded-full border border-foreground/15 transition-colors duration-300 group-hover:border-ai group-hover:bg-ai group-hover:text-primary-foreground">
                  <f.icon className="size-5" aria-hidden />
                </span>
                <span className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
              </div>
              <h3 className="mt-6 text-2xl font-black tracking-[-0.03em]">{f.title}</h3>
              <p className="mt-2 max-w-prose text-[15px] leading-relaxed text-foreground-secondary">{f.body}</p>
              {f.points.length ? (
                <ul className="mt-auto flex flex-wrap gap-2 pt-6">
                  {f.points.map((p) => (
                    <li key={p.label} className="inline-flex items-center gap-1.5 rounded-full border border-foreground/15 px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                      <p.icon className="size-3.5" aria-hidden />
                      {p.label}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
