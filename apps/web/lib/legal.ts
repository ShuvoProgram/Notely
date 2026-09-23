/**
 * Facts the legal pages and footer are written against. Operators override the contact
 * address and governing jurisdiction per deployment with public env vars (safe to expose:
 * they are printed on public pages anyway).
 */
export const LEGAL = {
  productName: "Notely AI",
  companyName: "Notely AI",
  contactEmail: process.env.NEXT_PUBLIC_LEGAL_CONTACT_EMAIL ?? "support@notely.app",
  jurisdiction: process.env.NEXT_PUBLIC_LEGAL_JURISDICTION ?? "Bangladesh",
  /** ISO date of the last substantive change to either document. */
  lastUpdated: "2026-09-24",
} as const;

export function formatLegalDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}
