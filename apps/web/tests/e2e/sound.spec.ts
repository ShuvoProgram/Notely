import { expect, test, type Page } from "@playwright/test";

async function signup(page: Page) {
  const email = `e2e-sound-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Sound Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("a perfectly fine passphrase");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("sound preference is per user, applies immediately and survives a reload", async ({ page }) => {
  await signup(page);
  await page.goto("/app/settings/notifications");
  const toggle = page.getByRole("switch", { name: "Play sounds" });
  await expect(toggle).toBeChecked();
  await expect(page.getByText("60%")).toBeVisible();

  // Volume: keyboard-drive the slider and make sure the value is saved server-side.
  const slider = page.getByRole("slider", { name: "Sound volume" });
  await slider.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByText("50%")).toBeVisible();
  await expect.poll(async () => (await (await page.request.get("/api/v1/users/me")).json()).data.sound.volume).toBe(0.5);

  // Off means off: the switch persists and the volume controls go quiet.
  const savedOff = page.waitForResponse((r) => r.request().method() === "PATCH" && r.url().includes("/users/me"));
  await toggle.click();
  await savedOff;
  await expect(toggle).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Preview" })).toBeDisabled();

  await page.reload();
  await expect(page.getByRole("switch", { name: "Play sounds" })).not.toBeChecked();
  await expect(page.getByText("50%")).toBeVisible();
  // The player mirrors the saved preference locally so it is silent before /users/me resolves.
  expect(JSON.parse(await page.evaluate(() => localStorage.getItem("notely.sound") ?? "{}"))).toEqual({ enabled: false, volume: 0.5 });
});
