import type { Metadata } from "next";
import Link from "next/link";

import { LegalArticle, LegalSection, LegalToc } from "@/components/site/legal-page";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `How ${LEGAL.productName} collects, uses, stores, shares, protects and deletes your information, including Google user data from Gmail, Google Calendar, Google Drive, Google Docs, Google Sheets and Google Meet.`,
  alternates: { canonical: "/privacy-policy" },
  openGraph: { title: `Privacy Policy · ${LEGAL.productName}`, type: "article" },
  robots: { index: true, follow: true },
};

const SECTIONS = [
  { id: "information-we-collect", title: "Information we collect" },
  { id: "how-we-use-information", title: "How we use information" },
  { id: "accounts-and-authentication", title: "Accounts and authentication" },
  { id: "connected-tools", title: "Connected tools and integrations" },
  { id: "google-user-data", title: "Google OAuth and Google user data" },
  { id: "ai-features", title: "AI features and your own model keys" },
  { id: "sharing", title: "How we share information" },
  { id: "cookies", title: "Cookies and similar technologies" },
  { id: "storage-and-security", title: "Data storage and security" },
  { id: "retention-and-deletion", title: "Data retention and deletion" },
  { id: "your-rights", title: "Your rights and choices" },
  { id: "third-party-links", title: "Third-party services" },
  { id: "children", title: "Children's privacy" },
  { id: "changes", title: "Changes to this policy" },
  { id: "contact", title: "Contact" },
];

/**
 * Every Google API scope Notely can request, grouped by product. Keep this in sync with the
 * scopes of the providers in apps/api/app/integrations/google/*: Google's OAuth
 * verification checks that the privacy policy discloses each data type the app requests.
 */
const GOOGLE_DATA: { product: string; scopes: string[]; access: string; purpose: string; stored: string }[] = [
  {
    product: "Google Sign-In",
    scopes: ["openid", "email", "profile"],
    access: "Your name, email address, profile picture and Google account ID.",
    purpose: "To create your Notely account and sign you in with Google.",
    stored: "Name, email, picture URL and account ID are stored with your account.",
  },
  {
    product: "Gmail",
    scopes: ["gmail.readonly", "gmail.compose (optional)", "gmail.send (optional)"],
    access: "Message metadata (sender, recipients, subject, date), message text and labels of the emails you or the assistant look up; with the optional permissions, drafts and emails you ask Notely to create or send.",
    purpose: "To search and summarise your email when you ask, to turn emails into notes or tasks, and to draft or send an email only after you approve that specific message.",
    stored: "Not copied in bulk. Only the excerpts shown in an assistant conversation or an automation run you started are kept, in that conversation or run history.",
  },
  {
    product: "Google Calendar",
    scopes: ["calendar.readonly", "calendar.events (optional)"],
    access: "Your calendars and the events in them (title, time, attendees, location, description).",
    purpose: "To show upcoming events and answer questions about your schedule; with the optional permission, to create or update events for tasks you choose to put on your calendar.",
    stored: "For tasks you sync, the linked event ID and link. Event details are otherwise not stored.",
  },
  {
    product: "Google Drive",
    scopes: ["drive.readonly", "drive.metadata.readonly", "drive.file (optional)"],
    access: "File names, types, owners, modified dates and the contents of files you or the assistant open; with the optional permission, files that Notely creates for you.",
    purpose: "To find and read files you ask about and to attach or reference them in notes; with the optional permission, to save files you ask Notely to create.",
    stored: "Only excerpts shown in a conversation or automation run you started, and any content you choose to save into a note.",
  },
  {
    product: "Google Docs",
    scopes: ["documents.readonly", "documents (optional)", "drive.metadata.readonly"],
    access: "The title and text of documents you or the assistant open; with the optional permission, documents Notely creates or edits for you.",
    purpose: "To read, summarise or import a document you ask about; with the optional permission, to create or update a document after you approve it.",
    stored: "Only excerpts shown in a conversation or automation run you started, and any content you save into a note.",
  },
  {
    product: "Google Sheets",
    scopes: ["spreadsheets.readonly", "spreadsheets (optional)", "drive.metadata.readonly"],
    access: "Spreadsheet names and the cell values of sheets you or the assistant open; with the optional permission, rows Notely adds or updates for you.",
    purpose: "To read and summarise data you ask about and, with the optional permission, to append or update rows (for example in an automation you set up and approve).",
    stored: "Only the values shown in a conversation or automation run you started.",
  },
  {
    product: "Google Meet",
    scopes: ["meetings.space.readonly", "meetings.space.created (optional)", "userinfo.email"],
    access: "Details of Meet spaces (meeting link, code and settings); with the optional permission, meeting spaces Notely creates for you.",
    purpose: "To add a Meet link to an event or task when you ask for one.",
    stored: "The meeting link, if you save it into a note, task or event.",
  },
];

export default function PrivacyPolicyPage() {
  const contact = <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>;
  return (
    <LegalArticle
      title="Privacy Policy"
      intro={`${LEGAL.productName} ("Notely", "we", "us") is a note-taking workspace with an AI assistant that can read from and act on tools you choose to connect, such as Gmail, Google Calendar and Google Drive. This policy explains what information we collect, how we use it, how we store, share and protect it, how long we keep it, and how you can delete it. We only collect what the product needs, we never sell your data, and we never use your data to train AI models.`}
    >
      <LegalToc items={SECTIONS} />

      <LegalSection id="information-we-collect" title="1. Information we collect">
        <p>
          <strong>Account information.</strong> Your email address, display name and, if you sign in with Google, the name,
          email address, profile picture and account identifier Google shares with us. If you create a password, we store
          only a salted hash of it. If you upload a profile picture, we store a resized copy of it.
        </p>
        <p>
          <strong>Content you create.</strong> Notes, folders, tags, tasks, reminders, automations and anything you type or
          paste into Notely, including messages you send to the AI assistant and the assistant’s replies.
        </p>
        <p>
          <strong>Data from connected tools.</strong> When you connect a tool (for example Gmail, Google Calendar or Google
          Drive), we access only the data allowed by the permissions you approved, and only when you or the assistant ask
          for it. Section 5 lists exactly which Google data we access and why. Where a connector can write (send an email,
          create an event, add a spreadsheet row), nothing is written until you approve that specific action.
        </p>
        <p>
          <strong>Technical and usage information.</strong> Browser type, device and operating system, IP address, the
          pages and features you use, timestamps, and diagnostic logs such as error reports and request identifiers.
        </p>
      </LegalSection>

      <LegalSection id="how-we-use-information" title="2. How we use information">
        <ul>
          <li>To provide the service: store and sync your notes and tasks, run searches, and power the AI assistant.</li>
          <li>To carry out what you ask the assistant or an automation to do in your connected tools, with your approval for any change.</li>
          <li>To keep your account secure: sign you in, detect abuse, rate-limit requests and investigate incidents.</li>
          <li>To operate and fix Notely: measure reliability and performance and resolve errors.</li>
          <li>To contact you about your account, security and material changes to the service.</li>
          <li>To comply with law and enforce our <Link href="/terms-and-conditions">Terms &amp; Conditions</Link>.</li>
        </ul>
        <p>
          We do not sell personal information, we do not use it for advertising, and we do not use your notes, messages or
          connected-tool data to train machine-learning models.
        </p>
      </LegalSection>

      <LegalSection id="accounts-and-authentication" title="3. Accounts and authentication">
        <p>
          You can create an account with an email address and password, or by continuing with Google. With Google sign-in
          we receive your verified email address, name, profile picture and account identifier; we never receive or store
          your Google password. Sessions are kept in a secure, HTTP-only cookie, and you can review and sign out other
          sessions and turn on two-factor authentication in <em>Settings → Security</em>.
        </p>
      </LegalSection>

      <LegalSection id="connected-tools" title="4. Connected tools and integrations">
        <p>
          Connecting a tool is always your choice and always goes through that vendor’s own consent (OAuth) screen, where
          you can see exactly which permissions are requested. Write permissions are optional and can be left off. You can
          disconnect a tool at any time from <em>Settings → Connections</em>.
        </p>
        <p>
          The access and refresh tokens a vendor issues are encrypted at rest and used only to make the requests you, the
          assistant or your automations initiate. When you disconnect a tool we revoke the token with the vendor (where the
          vendor supports it) and delete it from our systems.
        </p>
      </LegalSection>

      <LegalSection id="google-user-data" title="5. Google OAuth and Google user data">
        <p>
          This section describes how Notely accesses, uses, stores, shares, protects, retains and deletes data we receive
          from Google APIs (“Google user data”). You choose which Google products to connect, and optional permissions are
          only requested if you turn them on.
        </p>

        <h3 className="pt-2 text-base font-semibold">5.1 What we access and why</h3>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[640px] border-collapse text-left text-sm leading-6">
            <thead className="bg-muted/40">
              <tr>
                <th scope="col" className="border-b p-3 font-semibold">Google product and permissions</th>
                <th scope="col" className="border-b p-3 font-semibold">Data accessed</th>
                <th scope="col" className="border-b p-3 font-semibold">Why we use it</th>
                <th scope="col" className="border-b p-3 font-semibold">What we store</th>
              </tr>
            </thead>
            <tbody>
              {GOOGLE_DATA.map((row) => (
                <tr key={row.product} className="align-top">
                  <th scope="row" className="border-b p-3 font-semibold">
                    {row.product}
                    <span className="mt-1 block font-mono text-xs font-normal text-muted-foreground">{row.scopes.join(", ")}</span>
                  </th>
                  <td className="border-b p-3">{row.access}</td>
                  <td className="border-b p-3">{row.purpose}</td>
                  <td className="border-b p-3">{row.stored}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 className="pt-2 text-base font-semibold">5.2 How we use Google user data</h3>
        <ul>
          <li>Only to provide and improve the user-facing features you can see and control in Notely, as described in the table above.</li>
          <li>Only when you, or an automation you created and switched on, ask for it. Notely does not scan your Google account in the background.</li>
          <li>Any change to your Google data (sending an email, creating an event, editing a document or sheet) happens only after you approve that specific action.</li>
          <li>Never for advertising, never to build user profiles, and never sold.</li>
        </ul>

        <h3 className="pt-2 text-base font-semibold">5.3 How we store and protect it</h3>
        <p>
          We do not keep a copy of your mailbox, calendar or files. Google user data is fetched when needed, and only the
          pieces shown to you are kept: in the assistant conversation or automation run history where you requested them,
          or in a note or task if you choose to save them there. Your Google OAuth tokens are encrypted at rest with an
          application-level key, all data is encrypted in transit (TLS), and access to production systems is restricted to
          authorized personnel.
        </p>

        <h3 className="pt-2 text-base font-semibold">5.4 How we share it</h3>
        <p>
          We do not sell or transfer Google user data to third parties, except: (a) to the AI model provider that answers
          your request, which receives only the excerpts needed for that request (see section 6); (b) to service providers
          that host and operate Notely on our behalf under confidentiality obligations; (c) when required by law; or
          (d) with your explicit consent. Humans at Notely do not read your Google user data unless you ask us to for
          support, it is necessary for security purposes (such as investigating abuse), or it is required by law.
        </p>

        <h3 className="pt-2 text-base font-semibold">5.5 Retention and deletion</h3>
        <ul>
          <li>Google OAuth tokens are kept while the connection is active and deleted as soon as you disconnect the Google product in <em>Settings → Connections</em>.</li>
          <li>Excerpts in an assistant conversation are deleted when you delete that conversation; excerpts in an automation’s run history are deleted when you delete the automation.</li>
          <li>Content you saved into notes or tasks stays until you delete it (deleted notes are removed permanently 30 days after being moved to Trash).</li>
          <li>You can also revoke Notely’s access at any time from your Google Account at <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer">myaccount.google.com/permissions</a>.</li>
          <li>To have all of your Google user data and your account deleted, email {contact}; we complete deletion within 30 days.</li>
        </ul>

        <h3 className="pt-2 text-base font-semibold">5.6 Limited Use</h3>
        <p>
          {LEGAL.productName}’s use and transfer to any other app of information received from Google APIs will adhere to
          the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noopener noreferrer">
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements.
        </p>
        <p>
          We do not use Google Workspace API data (such as Gmail, Calendar, Drive, Docs, Sheets or Meet data) to develop,
          improve or train generalized or non-personalized AI and/or machine-learning models.
        </p>
      </LegalSection>

      <LegalSection id="ai-features" title="6. AI features and your own model keys">
        <p>
          To answer a request, the assistant sends the parts of your notes and connected-tool data needed for that request
          to a large-language-model provider. Which provider depends on this deployment’s configuration or, if you add your
          own model under <em>Settings → AI</em>, on the provider and key you choose. The provider processes that data only
          to generate the response. Your own API key is stored encrypted, is never shown again after you save it, and is
          used only for your requests. We choose providers and settings that do not use API data to train their models.
        </p>
      </LegalSection>

      <LegalSection id="sharing" title="7. How we share information">
        <p>
          We share information only with: service providers that host, store and operate Notely for us; the AI model
          provider that processes a request you make; the tools you connect, when you or an approved automation ask Notely
          to act in them; authorities when required by law or to protect the rights and safety of users; and a successor
          if Notely is involved in a merger or acquisition, in which case this policy continues to apply. We do not sell
          personal information.
        </p>
      </LegalSection>

      <LegalSection id="cookies" title="8. Cookies and similar technologies">
        <p>
          Notely uses strictly necessary cookies: a session cookie that keeps you signed in and a security cookie that
          protects forms from cross-site request forgery. We do not use advertising or cross-site tracking cookies. Your
          browser’s local storage holds preferences such as theme and may briefly hold unsaved note edits so they survive a
          crash. Clearing cookies and site data signs you out.
        </p>
      </LegalSection>

      <LegalSection id="storage-and-security" title="9. Data storage and security">
        <p>
          Data is stored on servers operated by our hosting provider and is encrypted in transit (TLS). OAuth tokens and your
          own AI keys are additionally encrypted with an application-level key. Access to production systems is restricted
          to authorized personnel. No method of transmission or storage is completely secure; if we learn of a breach
          affecting your data we will notify you and the relevant authorities as required by law.
        </p>
      </LegalSection>

      <LegalSection id="retention-and-deletion" title="10. Data retention and deletion">
        <ul>
          <li>Notes and other content stay until you delete them. Notes moved to Trash are permanently deleted after 30 days, or immediately if you delete them forever.</li>
          <li>Assistant conversations stay until you delete them; automations and their run history stay until you delete the automation.</li>
          <li>Connected-tool tokens are deleted when you disconnect the tool.</li>
          <li>Expired sign-in sessions are removed automatically.</li>
          <li>To delete your account and all associated data, email {contact} from the address on your account. We delete it from active systems within 30 days and from backups within 90 days, except records we must keep by law.</li>
        </ul>
      </LegalSection>

      <LegalSection id="your-rights" title="11. Your rights and choices">
        <p>
          Depending on where you live, you may have the right to access, correct, export, restrict or delete your personal
          data, to object to certain processing, and to complain to a supervisory authority. In Notely you can edit your
          profile, delete notes, tasks, conversations and automations, disconnect tools and sign out other sessions. For
          anything else, including a copy of your data or deleting your account, contact us at {contact}; we respond within
          30 days.
        </p>
      </LegalSection>

      <LegalSection id="third-party-links" title="12. Third-party services">
        <p>
          Tools you connect (such as Google, Microsoft, Notion, Slack, Atlassian Jira, Asana, ClickUp, Todoist, Dropbox and
          Zoom) are operated by their vendors under their own privacy policies, and notes may contain links to other sites.
          We are not responsible for their practices and encourage you to read their policies.
        </p>
      </LegalSection>

      <LegalSection id="children" title="13. Children's privacy">
        <p>
          Notely is not directed to children under 16 (or the higher age required in your country), and we do not knowingly
          collect personal information from them. If you believe a child has given us personal information, contact us and
          we will delete it.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="14. Changes to this policy">
        <p>
          We may update this policy as Notely evolves. We will post the new version here and update the date at the top; for
          material changes, especially to how we use Google user data, we will notify you by email or in the app before they
          take effect.
        </p>
      </LegalSection>

      <LegalSection id="contact" title="15. Contact">
        <p>
          Questions, requests or concerns about privacy or your data: {contact}. Please include enough detail for us to
          identify your account and your request.
        </p>
      </LegalSection>
    </LegalArticle>
  );
}
