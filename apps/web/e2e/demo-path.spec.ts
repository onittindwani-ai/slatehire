import { expect, test } from "@playwright/test";
import { appId, call, login, resetDemo, signOut, watch } from "./helpers";

test("the five minute demo path, with no accounts", async ({ page }) => {
  const errors = watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await resetDemo(page);
  // 1 the pipeline: 90 applicants, every evidence quote found in its resume
  await page.goto("/");
  await expect(page.getByText("Evidence quotes found in the resume")).toBeVisible();
  await expect(page.getByLabel("Hiring pipeline")).toBeVisible();
  // 2 blind mode: an applicant in Applied has no name, no email and the switch is locked
  const applied = await appId(page, "applied");
  await page.goto(`/candidates/${applied}`);
  await expect(page.getByRole("heading", { level: 1, name: /^Candidate A\d+$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Blind view on" })).toBeDisabled();
  await expect(page.getByText("@mail.example.test")).toHaveCount(0);
  await expect(page.locator(".cf-id").first()).toBeVisible();
  // 3 evidence: pointing at a criterion marks the exact words in the resume
  const row = page.locator(".cf-crit__row:not([disabled])").first();
  await row.hover();
  await expect(page.locator("mark.cf-ev").first()).toBeVisible();
  // 4 a decline needs a reason written by a person
  await page.getByRole("button", { name: "Decline" }).click();
  const move = page.getByRole("button", { name: "Move", exact: true });
  await expect(move).toBeDisabled();
  await page.getByLabel(/Reason/).fill("The role needs written examples and none were shown.");
  await move.click();
  await expect(page.getByText("Moved to Declined.").first()).toBeVisible();
  // 5 shortlist another, then identity can be shown (and the server records it)
  const second = await appId(page, "applied", 1);
  await page.goto(`/candidates/${second}`);
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(page.getByText("Moved to Shortlisted.").first()).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Blind view on" }).click();
  await expect(page.getByRole("button", { name: "Identity shown" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();
  // 6 plan an interview from the workspace
  await page.getByRole("button", { name: "Plan an interview" }).click();
  await page.getByRole("button", { name: "Plan it" }).click();
  await expect(page.getByText("Interview planned").first()).toBeVisible();
  // 7 an offer waits for a second person: the person who asked cannot approve
  await page.goto("/approvals");
  await expect(page.getByText("Waiting (1)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" }).first()).toBeDisabled(); // the person who asked cannot approve their own request
  await signOut(page);
  await login(page, "approver@example.test");
  await page.goto("/approvals");
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("Approved.").first()).toBeVisible();
  await page.goto("/offers");
  await page.getByRole("button", { name: "Write the offer file" }).click();
  await expect(page.getByText(/Offer file written/).first()).toBeVisible();
  await signOut(page);
  await login(page);
  // 8 the rubric is locked and signed, onboarding and fairness have data
  await page.goto("/roles");
  await expect(page.getByText(/Version 1 locked/).first()).toBeVisible();
  await page.goto("/onboarding");
  await expect(page.getByText("30 days").first()).toBeVisible();
  await page.goto("/fairness");
  await page.getByRole("button", { name: "Run the report" }).click();
  await expect(page.getByText("Shortlisted from all applicants")).toBeVisible();
  await expect(page.getByText(/not legal advice/i).first()).toBeVisible();
  // 9 Run now brings the next application email and scores it, and the audit chain holds
  await page.goto("/");
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText(/Ran the jobs/).first()).toBeVisible();
  await page.goto("/audit");
  await expect(page.getByText("Chain intact")).toBeVisible();
  expect(errors.filter((e) => !/409|400/.test(e))).toEqual([]);
});
