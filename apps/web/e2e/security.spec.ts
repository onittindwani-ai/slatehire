import { expect, test } from "@playwright/test";
import { login, resetDemo } from "./helpers";

test("a change without the required header is refused and the login route is not exposed", async ({ page }) => {
  await login(page);
  await resetDemo(page);
  const bare = await page.request.post("/api/demo/tick", { data: {} });
  expect(bare.status()).toBe(400);
  const direct = await page.request.post("/api/auth/login", { headers: { "x-slatehire": "1" }, data: { email: "owner@example.test", password: "demo-password-1" } });
  expect(direct.status()).toBe(404);
  const ok = await page.request.post("/api/demo/tick", { headers: { "x-slatehire": "1", "content-type": "application/json" }, data: {} });
  expect(ok.ok()).toBeTruthy();
});
