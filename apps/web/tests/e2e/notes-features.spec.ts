import { expect, test, type Page } from "@playwright/test";

// These flows chain several saves and reloads; give them room.
test.describe.configure({ timeout: 90_000 });

const password = "a perfectly fine passphrase";

async function signup(page: Page, who = "features") {
  const email = `e2e-notes-${who}-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Notes Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
  return email;
}

async function createNote(page: Page, title: string) {
  await page.goto("/app/notes");
  await page.getByRole("complementary", { name: "Notes list" }).getByRole("button", { name: "New note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);
  await page.getByLabel("Note title").fill(title);
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  return page.url().split("/").pop() as string;
}

function listTitles(page: Page) {
  return page.getByRole("complementary", { name: "Notes list" }).locator("li a > div > p");
}

async function openFromList(page: Page, title: string, isMobile: boolean) {
  if (isMobile) await page.goto("/app/notes");
  await page.getByRole("complementary", { name: "Notes list" }).getByText(title, { exact: true }).click();
  await expect(page.getByLabel("Note title")).toHaveValue(title);
}

test("opening a note does not change its position; editing moves it to the top", async ({ page, isMobile }) => {
  await signup(page);
  await createNote(page, "Alpha");
  await createNote(page, "Beta");
  await createNote(page, "Gamma");
  if (isMobile) await page.goto("/app/notes");
  await expect(listTitles(page).first()).toHaveText("Gamma");

  // Open the oldest, then the middle one, and go back: the order must be untouched.
  await openFromList(page, "Alpha", isMobile);
  await page.waitForTimeout(1500); // longer than the autosave debounce — nothing may be saved
  await openFromList(page, "Beta", isMobile);
  await page.waitForTimeout(1500);
  await page.goto("/app/notes");
  await expect(listTitles(page)).toHaveText(["Gamma", "Beta", "Alpha"]);

  // A real edit is what moves a note up.
  await openFromList(page, "Alpha", isMobile);
  const body = page.getByRole("textbox", { name: "Note body" });
  await body.click();
  await body.pressSequentially("An actual change.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await page.goto("/app/notes");
  await expect(listTitles(page).first()).toHaveText("Alpha");
});

test("background colour, reminder and version history", async ({ page, isMobile }) => {
  await signup(page);
  const id = await createNote(page, "Design review");
  const body = page.getByRole("textbox", { name: "Note body" });
  await body.click();
  await body.pressSequentially("First draft of the review.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });

  // Colour is persisted on the note and survives a reload.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Change background" }).click();
  const background = page.getByRole("dialog", { name: "Note background" });
  await background.getByRole("radio", { name: "Blue" }).click();
  const saved = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes("/notes/") && (r.request().postData() ?? "").includes("color"));
  await background.getByRole("button", { name: "Apply" }).click();
  await saved;
  await expect(background).toBeHidden();
  await expect(page.locator("article[data-note-color='blue']")).toBeVisible();
  await page.reload();
  await expect(page.locator("article[data-note-color='blue']")).toBeVisible();
  // A custom colour is typed as hex, previewed, and kept as a soft tint.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Change background" }).click();
  await background.getByLabel("Custom colour").fill("#8AA1C1");
  const savedHex = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes("/notes/") && (r.request().postData() ?? "").includes("color"));
  await background.getByRole("button", { name: "Apply" }).click();
  await savedHex;
  await expect(page.locator("article[data-note-color='custom']")).toHaveAttribute("style", /8aa1c1/);

  // Reminder: one entry point (More → Set reminder). The dialog stays open until the user acts.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Set reminder" }).click();
  const reminder = page.getByRole("dialog", { name: "Remind me" });
  await expect(reminder).toBeVisible();
  await page.waitForTimeout(500);
  await expect(reminder).toBeVisible(); // did not close itself after the menu went away
  await reminder.getByRole("button", { name: "Tomorrow" }).click();
  await expect(reminder.getByLabel("Time", { exact: true })).toHaveText(/9:00 AM/);
  await reminder.getByRole("button", { name: "Set reminder" }).click();
  await expect(reminder).toBeHidden();
  await expect(page.locator("article").getByText(/Tomorrow, 9:00 AM/)).toBeVisible();
  if (isMobile) await page.goto("/app/notes");
  await expect(page.getByRole("complementary", { name: "Notes list" }).getByText(/Tomorrow, /)).toBeVisible();
  await openFromList(page, "Design review", isMobile);
  // Edit via the same dialog, remove via the menu.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Edit reminder" }).click();
  await expect(page.getByRole("dialog", { name: "Edit reminder" })).toBeVisible();
  await page.getByRole("dialog", { name: "Edit reminder" }).getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Remove reminder" }).click();
  await expect(page.locator("article").getByText(/Tomorrow, 9:00 AM/)).toHaveCount(0);

  // Version history. The very first edit (the title) snapshotted the empty note; keystrokes
  // inside the snapshot window collapse into it, so there is exactly one version now.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Version history" }).click();
  const dialog = page.getByRole("dialog", { name: "Version history" });
  const versions = dialog.getByRole("complementary", { name: "Versions" }).getByRole("button");
  await expect(versions).toHaveCount(1);
  await versions.first().click();
  await expect(dialog.getByRole("textbox", { name: "Note body" })).toBeVisible();
  await dialog.getByRole("button", { name: "Restore this version" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByLabel("Note title")).toHaveValue("");
  await expect(body).not.toContainText("First draft");

  // The state before the restore was kept, so the restore itself can be undone.
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Version history" }).click();
  await dialog.getByText("Before a restore").click();
  await expect(dialog.getByRole("textbox", { name: "Note body" })).toContainText("First draft of the review.");
  await dialog.getByRole("button", { name: "Restore this version" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByLabel("Note title")).toHaveValue("Design review");
  await expect(body).toContainText("First draft of the review.");

  // Editing continues from the restored version (no false conflict) and persists.
  await body.click();
  await body.press("End");
  await body.pressSequentially(" Plus a follow-up.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Note body" })).toContainText("First draft of the review. Plus a follow-up.");
  expect(id).toMatch(/[0-9a-f-]{36}/);
});

test("share a note by email: the guest sees it under Shared and cannot edit as a viewer", async ({ browser, page }) => {
  const guestEmail = `e2e-notes-guest-${Date.now()}@example.com`;
  await signup(page, "owner");
  await createNote(page, "Team charter");

  await page.getByRole("button", { name: /^Share( \d+)?$/ }).click();
  const share = page.getByRole("dialog", { name: /Share/ });
  await share.getByLabel("Email address").fill(guestEmail);
  await share.getByRole("button", { name: "Invite" }).click();
  await expect(share.getByText(guestEmail)).toBeVisible();
  // No SMTP in the test environment: the app says so, with the exact fix, instead of "sent".
  await expect(page.getByText("Unable to send invitation")).toBeVisible();
  await expect(share.getByText(/SMTP_HOST/)).toBeVisible();
  await expect(share.getByText("Invited — waiting for them to open the email")).toBeVisible();
  await expect(page.getByText("Unable to send invitation")).toBeHidden({ timeout: 15_000 }); // toast gone (it can cover the form on phones)
  // A second click for the same address is refused rather than sending twice.
  await share.getByLabel("Email address").fill(guestEmail);
  await share.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText("Invitation already sent")).toBeVisible();
  await share.getByLabel("Email address").fill("not an email");
  await share.getByRole("button", { name: "Invite" }).click();
  await expect(share.getByText("Enter a valid email address.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: /Shared with 1/ })).toBeVisible();

  // The guest signs up with that email and finds the note under Shared, read-only.
  const guestContext = await browser.newContext();
  const guest = await guestContext.newPage();
  await guest.goto("/signup");
  await guest.getByLabel("Name").fill("Guest");
  await guest.getByLabel("Email").fill(guestEmail);
  await guest.getByLabel("Password", { exact: true }).fill(password);
  await guest.getByRole("button", { name: "Create account" }).click();
  await expect(guest).toHaveURL(/\/app$/);
  await guest.goto("/app/notes?view=shared");
  await guest.getByRole("complementary", { name: "Notes list" }).getByText("Team charter").click();
  await expect(guest.getByText(/Shared with you as a viewer/)).toBeVisible();
  await expect(guest.getByLabel("Note title")).toHaveAttribute("readonly", "");
  // A notification was raised for the share.
  await guest.getByRole("button", { name: /Notifications/ }).click();
  await expect(guest.getByRole("list", { name: "Notifications" }).getByText(/shared/i).first()).toBeVisible();

  // Owner promotes them to editor; the guest can now type.
  await page.getByRole("button", { name: /^Share( \d+)?$/ }).click();
  await share.getByLabel(`Role for ${guestEmail}`).click();
  await page.getByRole("option", { name: "Can edit" }).click();
  await expect(share.getByText("Has access")).toBeVisible();
  await page.keyboard.press("Escape");
  await guest.reload();
  await expect(guest.getByLabel("Note title")).not.toHaveAttribute("readonly", "");
  const guestBody = guest.getByRole("textbox", { name: "Note body" });
  await guestBody.click();
  await guestBody.pressSequentially("Added by the guest.");
  await expect(guest.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await guestContext.close();
});

test("select several notes and move them to trash in one go", async ({ page, isMobile }) => {
  await signup(page);
  await createNote(page, "Keep me");
  await createNote(page, "Bin one");
  await createNote(page, "Bin two");
  if (isMobile) await page.goto("/app/notes");
  const list = page.getByRole("complementary", { name: "Notes list" });
  await list.getByRole("button", { name: "Select notes" }).click();
  await list.getByRole("checkbox", { name: "Select Bin two" }).click();
  await list.getByRole("checkbox", { name: "Select Bin one" }).click({ modifiers: ["Shift"] }); // range: Bin two → Bin one
  await expect(list.getByText("2 selected")).toBeVisible();
  await expect(list.getByRole("checkbox", { name: "Select Keep me" })).not.toBeChecked();
  // Moving to trash is reversible, so it runs straight away and offers Undo (no confirmation).
  await list.getByRole("button", { name: "Move to trash" }).click();
  await expect(page.getByText("Moved 2 notes to trash")).toBeVisible();
  await expect(page.locator("[data-sonner-toast]").getByRole("button", { name: "Undo" })).toBeVisible();
  await expect(listTitles(page)).toHaveText(["Keep me"]);
  await page.getByRole("tab", { name: "Trash" }).click();
  await expect(listTitles(page)).toHaveCount(2); // trashed together → same timestamp, order not guaranteed
  expect((await listTitles(page).allTextContents()).sort()).toEqual(["Bin one", "Bin two"]);

  // Select all + cancel leaves everything untouched; an invalid invitation link is explained.
  await page.getByRole("tab", { name: "Notes" }).click();
  await list.getByRole("button", { name: "Select notes" }).click();
  await list.getByRole("checkbox", { name: "Select all" }).click();
  await expect(list.getByText("1 selected")).toBeVisible();
  await list.getByRole("checkbox", { name: "Deselect all" }).click();
  await expect(list.getByText("Select notes")).toBeVisible();
  // Escape leaves selection mode; so does Cancel.
  await page.keyboard.press("Escape");
  await expect(list.getByRole("toolbar", { name: "Selection" })).toHaveCount(0);
  await list.getByRole("button", { name: "Select notes" }).click();
  await list.getByRole("button", { name: "Cancel selection" }).click();
  await expect(list.getByRole("toolbar", { name: "Selection" })).toHaveCount(0);
  await page.goto("/invite/not-a-real-token");
  await expect(page.getByRole("heading", { name: /invitation link isn’t valid/ })).toBeVisible();
});
