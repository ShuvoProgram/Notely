import type { Metadata } from "next";
import Link from "next/link";

import { LegalArticle, LegalSection, LegalToc } from "@/components/site/legal-page";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Terms & Conditions",
  description: `The terms that govern your use of ${LEGAL.productName}: accounts, acceptable use, connected tools, your content, availability, liability and termination.`,
  alternates: { canonical: "/terms-and-conditions" },
  openGraph: { title: `Terms & Conditions · ${LEGAL.productName}`, type: "article" },
  robots: { index: true, follow: true },
};

const SECTIONS = [
  { id: "acceptance", title: "Acceptance of these terms" },
  { id: "eligibility-and-accounts", title: "Eligibility and account responsibilities" },
  { id: "acceptable-use", title: "Acceptable use" },
  { id: "connected-tools", title: "Connected tools and integrations" },
  { id: "ai-assistant", title: "The AI assistant" },
  { id: "your-content", title: "Your content and data" },
  { id: "intellectual-property", title: "Intellectual property" },
  { id: "third-party-services", title: "Third-party services" },
  { id: "availability", title: "Service availability and changes" },
  { id: "disclaimers", title: "Disclaimers" },
  { id: "liability", title: "Limitation of liability" },
  { id: "indemnity", title: "Indemnity" },
  { id: "termination", title: "Termination" },
  { id: "changes", title: "Changes to these terms" },
  { id: "governing-law", title: "Governing law and disputes" },
  { id: "contact", title: "Contact" },
];

export default function TermsPage() {
  const contact = <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>;
  return (
    <LegalArticle
      title="Terms & Conditions"
      intro={`These terms are an agreement between you and ${LEGAL.companyName} ("Notely", "we", "us") for the use of the ${LEGAL.productName} web application, its AI assistant and its integrations (together, the "Service"). Please read them; by creating an account or using the Service you agree to them and to our Privacy Policy.`}
    >
      <LegalToc items={SECTIONS} />

      <LegalSection id="acceptance" title="1. Acceptance of these terms">
        <p>
          By signing up, signing in (including with Google or Microsoft) or otherwise using the Service you accept these
          terms and our <Link href="/privacy-policy">Privacy Policy</Link>. If you use the Service on behalf of an
          organisation, you confirm you are authorised to bind it, and “you” includes that organisation. If you do not agree,
          do not use the Service.
        </p>
      </LegalSection>

      <LegalSection id="eligibility-and-accounts" title="2. Eligibility and account responsibilities">
        <ul>
          <li>You must be at least 16 years old (or the age of digital consent where you live) and able to enter a binding contract.</li>
          <li>Provide accurate account information and keep it up to date.</li>
          <li>
            Keep your password and sessions secure. You are responsible for activity under your account; tell us promptly
            at {contact} if you suspect unauthorised use. You can review and revoke sessions in <em>Settings</em>.
          </li>
          <li>One person per account. Do not share credentials or transfer your account without our consent.</li>
        </ul>
      </LegalSection>

      <LegalSection id="acceptable-use" title="3. Acceptable use">
        <p>You agree not to, and not to let others:</p>
        <ul>
          <li>Break the law, infringe anyone’s rights, or store or share content that is unlawful, defamatory, harassing or malicious.</li>
          <li>Access accounts, data or systems you are not authorised to access, or probe, scan or test the Service’s security without written permission.</li>
          <li>Interfere with the Service — for example by sending abusive volumes of requests, scraping, or circumventing rate limits or access controls.</li>
          <li>Use the assistant or a connected tool to send spam, impersonate others, or take actions in a third-party account you are not entitled to take.</li>
          <li>Reverse-engineer, copy or resell the Service except as permitted by law or a separate agreement with us.</li>
          <li>Upload malware or content designed to manipulate the AI assistant into acting against a user’s interests.</li>
        </ul>
      </LegalSection>

      <LegalSection id="connected-tools" title="4. Connected tools and integrations">
        <p>
          You may connect third-party tools (such as Gmail, Google Calendar, Google Drive, Microsoft 365, Notion, Slack,
          Jira, Dropbox or ClickUp). Doing so is optional and uses the vendor’s own authorization flow.
          You are responsible for having the right to connect the account you connect, for complying with the vendor’s
          terms, and for the actions you approve. We access connected accounts only as your Privacy Policy describes and
          only to the extent of the permissions you granted. You can disconnect any tool at any time, which revokes and
          deletes the stored credentials.
        </p>
      </LegalSection>

      <LegalSection id="ai-assistant" title="5. The AI assistant">
        <p>
          The assistant generates text and proposes actions using large language models. Output can be inaccurate,
          incomplete or out of date, and you should review it before relying on it. Any action that changes data — in
          Notely or in a connected tool — is shown to you for approval first; approving it is your decision and your
          responsibility. Do not use the assistant for decisions where errors could cause serious harm (for example
          medical, legal or financial decisions) without independent verification.
        </p>
      </LegalSection>

      <LegalSection id="your-content" title="6. Your content and data">
        <p>
          You own the notes, files and other content you put into Notely and everything you fetch from your connected
          tools (“Your Content”). You grant us a limited, non-exclusive licence to host, process, transmit and display Your
          Content solely to operate and improve the Service for you, including sending relevant excerpts to the AI model
          provider configured for your account. We do not use Your Content to train machine-learning models, and we do not
          claim any other rights in it. You are responsible for Your Content and for having the rights needed to use it
          with the Service. You can delete Your Content at any time by deleting it in the Service, and you can ask us for a copy of it or to delete your account by contacting us.
        </p>
      </LegalSection>

      <LegalSection id="intellectual-property" title="7. Intellectual property">
        <p>
          The Service, including its software, design, logos and documentation, is owned by {LEGAL.companyName} and its
          licensors and is protected by copyright, trademark and other laws. Subject to these terms we grant you a
          personal, non-exclusive, non-transferable, revocable licence to use the Service. Third-party names and logos
          shown in the connectors marketplace belong to their respective owners and are used only to identify the tools
          you can connect; no affiliation or endorsement is implied. Feedback you send us may be used without obligation
          to you.
        </p>
      </LegalSection>

      <LegalSection id="third-party-services" title="8. Third-party services">
        <p>
          Connected tools and AI model providers are independent services with their own terms and privacy practices. We
          are not responsible for their availability, accuracy, security or conduct, for changes they make to their APIs,
          or for content you access through them. If a vendor suspends or limits our access, the related features may stop
          working.
        </p>
      </LegalSection>

      <LegalSection id="availability" title="9. Service availability and changes">
        <p>
          We aim for the Service to be available continuously but do not guarantee it. We may modify, suspend or
          discontinue features, connectors or the Service as a whole, and may impose limits (such as rate limits or
          storage quotas). Where reasonably possible we will give notice of material changes. Beta or preview features are
          provided as-is and may change or be withdrawn at any time.
        </p>
      </LegalSection>

      <LegalSection id="disclaimers" title="10. Disclaimers">
        <p>
          THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE” WITHOUT WARRANTIES OF ANY KIND, WHETHER EXPRESS, IMPLIED OR
          STATUTORY, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT,
          ACCURACY OR UNINTERRUPTED OPERATION, TO THE FULLEST EXTENT PERMITTED BY LAW. Some jurisdictions do not allow
          the exclusion of certain warranties, so some of these exclusions may not apply to you.
        </p>
      </LegalSection>

      <LegalSection id="liability" title="11. Limitation of liability">
        <p>
          TO THE FULLEST EXTENT PERMITTED BY LAW, {LEGAL.companyName.toUpperCase()} AND ITS OFFICERS, EMPLOYEES AND
          SUPPLIERS WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL OR PUNITIVE DAMAGES, OR FOR
          ANY LOSS OF DATA, PROFITS, REVENUE OR GOODWILL, ARISING FROM OR RELATED TO THE SERVICE, ACTIONS TAKEN BY THE
          AI ASSISTANT THAT YOU APPROVED, OR ANY CONNECTED TOOL. OUR TOTAL LIABILITY FOR ALL CLAIMS IN ANY TWELVE-MONTH
          PERIOD WILL NOT EXCEED THE GREATER OF THE AMOUNT YOU PAID US FOR THE SERVICE IN THAT PERIOD OR USD 100. Nothing
          in these terms limits liability that cannot be limited by law, including for fraud or for death or personal
          injury caused by negligence.
        </p>
      </LegalSection>

      <LegalSection id="indemnity" title="12. Indemnity">
        <p>
          You will defend and indemnify {LEGAL.companyName} against claims, damages and costs (including reasonable legal
          fees) arising from Your Content, your use of connected tools, or your breach of these terms or applicable law.
        </p>
      </LegalSection>

      <LegalSection id="termination" title="13. Termination">
        <p>
          You may stop using the Service at any time and ask us to delete your account by contacting us. We may suspend or
          terminate your access if you materially breach these terms, if required by law, or if continuing would create
          risk for us or other users; where practical we will notify you and give you a chance to get a copy of Your Content.
          Sections 6 through 12 and 15 survive termination.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="14. Changes to these terms">
        <p>
          We may revise these terms. We will post the updated version here and update the date at the top; for material
          changes we will notify you by email or in the app at least 14 days before they take effect. Using the Service
          after that date means you accept the revised terms.
        </p>
      </LegalSection>

      <LegalSection id="governing-law" title="15. Governing law and disputes">
        <p>
          These terms are governed by the laws of {LEGAL.jurisdiction}, without regard to conflict-of-law rules, and the
          courts of {LEGAL.jurisdiction} have exclusive jurisdiction over disputes arising from them, except that you may
          rely on mandatory consumer-protection laws of the country where you live. Before starting formal proceedings,
          please contact us so we can try to resolve the matter informally.
        </p>
      </LegalSection>

      <LegalSection id="contact" title="16. Contact">
        <p>
          Questions about these terms: {contact}.
        </p>
      </LegalSection>
    </LegalArticle>
  );
}
