import { expect, test, type Page } from "@playwright/test";

// Visual walkthrough used during design work: signs up, seeds content and screenshots the key
// screens. Only runs when SHOTS=1 so it never slows the normal suite.
test.skip(!process.env.SHOTS, "screenshot walkthrough only");

const OUT = process.env.SHOTS_DIR ?? "test-results/screens";
const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `shots-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Muhammad");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("walkthrough", async ({ page }, testInfo) => {
  const tag = testInfo.project.name;
  await signup(page);
  await page.screenshot({ path: `${OUT}/${tag}-home.png`, fullPage: true });

  await page.goto("/app/notes");
  await page.getByRole("button", { name: "Create your first note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);
  await page.getByLabel("Note title").fill("Product Launch Meeting");
  const body = page.getByRole("textbox", { name: "Note body" });
  await body.click();
  await body.pressSequentially(
    "Today we discussed the product launch plan for Q4. The team agreed that we should focus on the Saudi market first, with a targeted campaign for enterprise customers. Marketing will prepare the launch assets, and the product team will finalize the pricing by September 15.",
  );
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: `${OUT}/${tag}-editor.png`, fullPage: true });

  // Select some text → floating Ask AI menu.
  await page.evaluate(() => {
    const el = document.querySelector(".notely-editor p");
    if (!el?.firstChild) return;
    const range = document.createRange();
    range.setStart(el.firstChild, 20);
    range.setEnd(el.firstChild, 60);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    (el.closest(".notely-editor") as HTMLElement).focus();
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${tag}-selection.png` });

  await page.goto("/app/connections");
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/${tag}-connections.png`, fullPage: true });
  await page.goto("/app/connections/notion");
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/${tag}-provider.png`, fullPage: true });
  await page.getByRole("button", { name: "Connect" }).first().click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${tag}-connect-dialog.png` });
  await page.keyboard.press("Escape");

  await page.goto("/app/ai");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${tag}-ai.png`, fullPage: true });
  await page.goto("/app/tasks");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${tag}-tasks.png`, fullPage: true });
  await page.goto("/app/settings/ai");
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${tag}-settings.png`, fullPage: true });
});
