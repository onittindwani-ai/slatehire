import { expect, test } from "@playwright/test";
import { PAGES, appId, login, resetDemo, watch } from "./helpers";

test("every page loads without console errors", async ({ page }) => {
  const errors = watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  for (const p of [...PAGES, `/candidates/${await appId(page, "shortlisted")}`]) {
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1").first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("pipeline board by keyboard: focus a card, press Enter, read the sheet", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const card = page.locator('section[aria-label="Hiring pipeline"] [aria-label^="candidate "], [aria-label^="candidate "]').first();
  await expect(card).toBeVisible();
  await card.focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("button", { name: "Open workspace" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  // The Open button inside the card is a real button in the tab order.
  await card.getByRole("button", { name: /^Open candidate/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog").getByRole("button", { name: "Open workspace" })).toBeVisible();
});

test("a read only sign in can look and cannot change anything", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, "viewer@example.test");
  await expect(page.getByText("Read only.").first()).toBeVisible();
  const r = await page.request.post("/api/applications/1/move", { headers: { "x-slatehire": "1", "content-type": "application/json" }, data: { to: "shortlisted", note: "x" } });
  expect(r.status()).toBe(403);
  await page.goto("/candidates");
  await expect(page.locator("main h1").first()).toBeVisible();
});
