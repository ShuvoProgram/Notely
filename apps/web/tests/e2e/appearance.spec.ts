import { expect, test, type Page } from "@playwright/test";

async function signup(page: Page) {
  const email = `e2e-look-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Look Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("a perfectly fine passphrase");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

const html = (page: Page, attr: string) => page.locator("html").getAttribute(attr);
const saved = async (page: Page) => (await (await page.request.get("/api/v1/users/me")).json()).data.appearance;
const APPROVED = ["Starry moss", "Sunlit forest", "Mountain lake", "Meadow sky", "Mossy branch"];

test("only the approved backgrounds can be chosen; the choice previews, saves and survives a reload", async ({ page }) => {
  await signup(page);
  await page.goto("/app/settings/appearance");
  const backgrounds = page.getByRole("radiogroup", { name: "Background" });

  // Exactly the five images from public/assets, and no way to upload or paint your own.
  await expect(backgrounds.getByRole("radio")).toHaveCount(APPROVED.length);
  for (const name of APPROVED) await expect(backgrounds.getByRole("radio", { name })).toBeVisible();
  await expect(backgrounds.getByRole("radio", { name: "Starry moss" })).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText(/upload|solid color|gradient/i)).toHaveCount(0);

  // Picking one applies it to the whole app at once, served as an optimised image, and saves it.
  await backgrounds.getByRole("radio", { name: "Mountain lake" }).click();
  await expect.poll(() => html(page, "data-bg")).toBe("mountain-lake");
  const image = await page.locator(".app-backdrop").evaluate((el) => getComputedStyle(el, "::before").backgroundImage);
  expect(image).toContain("/_next/image?url=%2Fassets%2Fbg-4.png");
  expect((await page.request.get(image.match(/url\("?(.*?)"?\)/)![1]!)).ok()).toBeTruthy();
  await expect.poll(async () => (await saved(page)).background).toBe("mountain-lake");

  // Glass level, then fine-tuning on top of it.
  await page.getByRole("radiogroup", { name: "Glass effect" }).getByRole("radio", { name: "Strong" }).click();
  await expect.poll(() => html(page, "data-glass")).toBe("strong");
  await page.getByRole("slider", { name: "Background blur" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await saved(page)).blur).toBe(80);

  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Background" }).getByRole("radio", { name: "Mountain lake" })).toHaveAttribute("aria-checked", "true");
  expect(await html(page, "data-bg")).toBe("mountain-lake");
  await expect(page.getByText("80%")).toBeVisible();

  // Off: solid surfaces, no backdrop blur, blur/opacity can't be tuned.
  await page.getByRole("radiogroup", { name: "Glass effect" }).getByRole("radio", { name: "Off" }).click();
  await expect.poll(() => html(page, "data-glass")).toBe("off");
  expect(await page.locator("[data-slot=card]").first().evaluate((el) => getComputedStyle(el).backdropFilter)).toBe("none");
  await expect(page.getByRole("slider", { name: "Background blur" })).toHaveAttribute("data-disabled", "");

  // Reset puts everything back.
  await page.getByRole("button", { name: "Reset to default" }).click();
  await expect.poll(async () => (await saved(page)).background).toBe("starry-moss");
  expect(await saved(page)).toMatchObject({ glass: "medium", blur: null, opacity: null, border: null });
  await expect.poll(() => html(page, "data-bg")).toBe("starry-moss");
});

test("the API refuses anything but an approved background", async ({ page }) => {
  await signup(page);
  for (const background of ["custom", "aurora", "https://example.com/me.png"]) {
    const res = await page.request.patch("/api/v1/users/me", {
      data: { appearance: { background, glass: "medium", blur: null, opacity: null, border: null } },
      headers: { Origin: "http://localhost:3000" },
    });
    expect(res.status(), background).toBe(422);
  }
});
