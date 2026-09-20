import type { Metadata } from "next";
import Link from "next/link";

import { LegalArticle, LegalSection, LegalToc } from "@/components/site/legal-page";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `How ${LEGAL.productName} collects, uses, stores and protects your information, including data from tools you connect such as Google, Microsoft, Notion and Slack.`,
  alternates: { canonical: "/privacy-policy" },
  openGraph: { title: `Privacy Policy · ${LEGAL.productName}`, type: "article" },
  robots: { index: true, follow: true },
};

const SECTIONS = [
  { id: "information-we-collect", title: "Information we collect" },
  { id: "how-we-use-information", title: "How we use information" },
  { id: "accounts-and-authentication", title: "Accounts and authentication" },
  { id: "connected-tools", title: "Connected tools and integrations" },
  { id: "google-api-services", title: "Google OAuth and Google user data" },
  { id: "ai-features", title: "AI features and your own model keys" },
  { id: "cookies", title: "Cookies and similar technologies" },
  { id: "storage-and-security", title: "Data storage and security" },
  { id: "retention-and-deletion", title: "Data retention and deletion" },
  { id: "your-rights", title: "Your rights and choices" },
  { id: "third-party-links", title: "Third-party links and services" },
  { id: "children", title: "Children's privacy" },
  { id: "changes", title: "Changes to this policy" },
  { id: "contact", title: "Contact" },
];

export default function PrivacyPolicyPage() {
  const contact = <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>;
  return (
    <LegalArticle
      title="Privacy Policy"
      intro={`${LEGAL.productName} ("Notely", "we", "us") is a note-taking workspace with an AI assistant that can read from and act on tools you choose to connect. This policy explains what we collect, why, how it is protected, and the choices you have. We only collect what the product needs, and we never sell your data or use your notes to train AI models.`}
    >
      <LegalToc items={SECTIONS} />

      <LegalSection id="information-we-collect" title="1. Information we collect">
        <p>
          <strong>Account information.</strong> Your email address, display name and, if you sign in with Google or
          Microsoft, the profile picture and account identifier those providers share with us. If you create a password,
          we store only a salted hash of it.
        </p>
        <p>
          <strong>Content you create.</strong> Notes, folders, tags, tasks, comments and anything you type or paste into
          Notely, including messages you send to the AI assistant and the assistant’s replies.
        </p>
        <p>
          <strong>Data from connected tools.</strong> When you connect a tool (for example Gmail, Google Calendar, Google
          Drive, Notion, Slack or Jira), we access only the data that the permissions you approved allow, only when you or
          the assistant asks for it — for example the subject and sender of recent emails, upcoming calendar events, or a
          document’s title and text. Where a connector can write (send an email, create an event, post a message), nothing
          is written until you approve the specific action.
        </p>
        <p>
          <strong>Technical and usage information.</strong> Browser type, device and operating system, IP address,
          approximate location derived from it, the pages and features you use, timestamps, and diagnostic logs such as
          error reports and request identifiers.
        </p>
      </LegalSection>

      <LegalSection id="how-we-use-information" title="2. How we use information">
        <ul>
          <li>To provide the service: store and sync your notes, run searches, and power the AI assistant.</li>
          <li>To carry out what you ask the assistant to do across your connected tools, with your approval for any change.</li>
          <li>To keep your account secure: sign you in, detect abuse, rate-limit requests and investigate incidents.</li>
          <li>To operate and improve Notely: measure reliability and performance and fix bugs.</li>
          <li>To communicate with you about your account, security and material changes to the service.</li>
          <li>To comply with law and enforce our <Link href="/terms-and-conditions">Terms &amp; Conditions</Link>.</li>
        </ul>
        <p>
          We do not sell personal information, and we do not use your notes, messages or connected-tool data to train
          machine-learning models.
        </p>
      </LegalSection>

      <LegalSection id="accounts-and-authentication" title="3. Accounts and authentication">
        <p>
          You can create an account with an email address and password or by continuing with Google or Microsoft. With
          federated sign-in we receive your verified email address, name, profile picture and a stable account identifier
          from the provider; we do not receive or store your provider password. Sessions are kept in a secure, HTTP-only
          cookie. You can review and revoke active sessions from your account settings.
        </p>
      </LegalSection>

      <LegalSection id="connected-tools" title="4. Connected tools and integrations">
        <p>
          Connecting a tool is always your choice and always uses that vendor’s own authorization (OAuth) screen, where you
          can see exactly which permissions are requested. Before you are sent to the vendor, Notely shows you what the
          assistant will be able to do with the connection and what the vendor will receive. You can choose optional
          permissions, and you can disconnect a tool at any time from <em>Settings → Connections</em>.
        </p>
        <p>
          The access and refresh tokens a vendor issues are stored encrypted at rest and are used only to make the
          requests you or the assistant initiate. Disconnecting a tool revokes the token where the vendor supports it and
          deletes it from our systems. Data fetched from a tool to answer a question is not copied into your notes unless
          you or the assistant explicitly save it there.
        </p>
      </LegalSection>

      <LegalSection id="google-api-services" title="5. Google OAuth and Google user data">
        <p>
          Notely’s use and transfer of information received from Google APIs adheres to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer">
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements. Specifically:
        </p>
        <ul>
          <li>
            We request only the scopes needed for the features you enable (for example read-only access to Gmail messages,
            read-only access to calendar events, or read-only access to Drive files), and we ask for write scopes (such as
            sending email or creating events) only if you opt in to them.
          </li>
          <li>Google user data is used only to provide the Notely features you can see and control — never for advertising.</li>
          <li>
            We do not transfer Google user data to third parties except as necessary to provide those features (for
            example, sending relevant excerpts to the AI model provider you have chosen), to comply with law, or with your
            explicit consent.
          </li>
          <li>Humans do not read Google user data except with your permission for support, for security investigations, or as required by law.</li>
          <li>You can revoke Notely’s access at any time in Notely or at your Google Account’s third-party access settings.</li>
        </ul>
      </LegalSection>

      <LegalSection id="ai-features" title="6. AI features and your own model keys">
        <p>
          The assistant sends the parts of your notes and connected-tool data that are needed to answer a request to a
          large-language-model provider. Which provider depends on the deployment’s configuration or, if you add your own
          model under <em>Settings → AI</em>, on the provider and key you chose. Your own API key is stored encrypted, is
          never displayed again after you save it, and is used only for your requests. Model providers process the data
          under their own terms; we do not permit them to use it for training where the provider offers that control.
        </p>
      </LegalSection>

      <LegalSection id="cookies" title="7. Cookies and similar technologies">
        <p>
          Notely uses strictly necessary cookies: a session cookie that keeps you signed in and a security cookie that
          protects forms from cross-site request forgery. We do not use advertising or cross-site tracking cookies. Your
          browser’s local storage may hold a copy of unsaved note edits so they survive a crash; it is cleared once the
          server confirms the save. You can clear cookies and site data in your browser at any time; doing so signs you
          out.
        </p>
      </LegalSection>

      <LegalSection id="storage-and-security" title="8. Data storage and security">
        <p>
          Data is stored on servers operated by the deployment’s hosting provider and is encrypted in transit (TLS) and at
          rest. OAuth tokens and your own AI keys are additionally encrypted with an application-level key. Access to
          production systems is restricted to authorized personnel, logged, and protected by multi-factor authentication.
          No method of transmission or storage is completely secure; if we learn of a breach affecting your data we will
          notify you and the relevant authorities as required by law.
        </p>
      </LegalSection>

      <LegalSection id="retention-and-deletion" title="9. Data retention and deletion">
        <ul>
          <li>Notes and content stay until you delete them. Deleted notes go to Trash and are permanently removed after 30 days or when you empty Trash.</li>
          <li>Connected-tool tokens are deleted when you disconnect the tool or delete your account.</li>
          <li>Diagnostic logs are kept for up to 30 days; audit records of assistant actions are kept for 12 months so you can review what the assistant did.</li>
          <li>When you delete your account, your personal data and content are removed from active systems within 30 days and from backups within 90 days, except where we must keep records to comply with law.</li>
        </ul>
      </LegalSection>

      <LegalSection id="your-rights" title="10. Your rights and choices">
        <p>
          Depending on where you live, you may have the right to access, correct, export, restrict or delete your personal
          data, to object to certain processing, and to lodge a complaint with a supervisory authority. In Notely you can
          edit your profile, export your notes, disconnect tools, revoke sessions and delete your account from{" "}
          <em>Settings</em>. For anything else, contact us at {contact}; we respond within 30 days.
        </p>
      </LegalSection>

      <LegalSection id="third-party-links" title="11. Third-party links and services">
        <p>
          Notes and search results may contain links to third-party sites, and connected tools are operated by their
          vendors under their own privacy policies (for example Google, Microsoft, Notion, Slack, Atlassian, Dropbox,
          ClickUp, Stripe and PayPal). We are not responsible for their practices and encourage you to read their
          policies.
        </p>
      </LegalSection>

      <LegalSection id="children" title="12. Children's privacy">
        <p>
          Notely is not directed to children under 16 (or the higher age required in your country), and we do not knowingly
          collect personal information from them. If you believe a child has provided us with personal information, contact
          us and we will delete it.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="13. Changes to this policy">
        <p>
          We may update this policy as Notely evolves. We will post the new version here, update the date at the top and,
          for material changes, notify you by email or in the app before they take effect. Continued use after the
          effective date means you accept the updated policy.
        </p>
      </LegalSection>

      <LegalSection id="contact" title="14. Contact">
        <p>
          Questions, requests or concerns about privacy: {contact}. Please include enough detail for us to identify your
          account and the request.
        </p>
      </LegalSection>
    </LegalArticle>
  );
}
