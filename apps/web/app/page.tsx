import { redirect } from "next/navigation";

import { Features } from "@/components/landing/features";
import { HowItWorks } from "@/components/landing/how-it-works";
import { Integrations } from "@/components/landing/integrations";
import { OrbitHero } from "@/components/landing/orbit-hero";
import { RevealOnScroll } from "@/components/landing/reveal";
import { FinalCta, Trust } from "@/components/landing/trust";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { getCurrentUser } from "@/lib/api/server";

import "./landing.css";

const SECTIONS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#integrations", label: "Integrations" },
  { href: "#trust", label: "Trust" },
];

/*
 * Conversion path: what it is (hero) → how it works → what's in it → what it connects to → why
 * it's safe → one clear next step. Signed-in people go straight to the app.
 */
export default async function LandingPage() {
  const user = await getCurrentUser();
  if (user) redirect("/app");

  return (
    <div className="landing flex flex-1 flex-col">
      {/* Without JavaScript nothing animates, so nothing may start hidden either. */}
      <noscript>
        <style>{`.landing [data-reveal], .landing .landing-fade, .landing [data-pop], .landing [data-hero-word] { opacity: 1 !important } .landing [data-ring] { stroke-dashoffset: 0 !important }`}</style>
      </noscript>
      <SiteHeader sections={SECTIONS} />
      <main className="flex-1 overflow-x-clip">
        <OrbitHero />
        <HowItWorks />
        <Features />
        <Integrations />
        <Trust />
        <FinalCta />
      </main>
      <SiteFooter />
      <RevealOnScroll />
    </div>
  );
}
