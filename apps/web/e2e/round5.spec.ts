import { expect, test, type Page } from "@playwright/test";
import { appId, call, login, resetDemo, signOut } from "./helpers";

/** Round 5: every screen walked as a first time owner. One test per defect found. */
const toast = (page: Page, text: string | RegExp) => expect(page.locator("[data-sonner-toast]").filter({ hasText: text }).first()).toBeVisible();
const json = async (r: { json: () => Promise<unknown> }) => (await r.json()) as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

test.describe("Round 5", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page);
    await resetDemo(page);
  });

  test("a read only sign in sees switched off controls with a reason, not buttons that answer 403", async ({ page }) => {
    await signOut(page);
    await login(page, "viewer@example.test");
    const off = async (name: string | RegExp, exact = false) => { const b = page.getByRole("button", { name, exact }).first(); await expect(b).toBeVisible(); await expect(b).toBeDisabled(); };
    await off("Add applicants"); await off("Run now"); await off("+1 day");
    await page.goto("/roles"); await off("New role"); await off("Save"); await off("Write a fresh draft"); await off("Start a new version");
    await page.goto("/approvals"); await off("Approve", true); await off("Reject", true);
    await page.goto("/onboarding"); await off("Add a task"); await expect(page.locator("input[type=checkbox]").first()).toBeDisabled();
    await page.goto("/fairness"); await off("Run the report"); await off("Save the labels");
    await page.goto("/integrations"); await off("Test the one in use");
    await page.goto(`/candidates/${await appId(page, "applied")}`); await off("Shortlist", true); await off("Decline", true); await off(/Blind view on/);
    await page.goto(`/candidates/${await appId(page, "shortlisted")}`); await off("Plan an interview");
    await page.goto("/");
    await page.locator(".cf-cand").first().click();
    await off("Shortlist", true);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Meta+k");
    await expect(page.getByRole("option", { name: "Reset the demo data" })).toHaveCount(0);
    await expect(page.getByRole("option", { name: "Run the jobs now" })).toHaveCount(0);
  });

  test("the command palette has the actions it should, and G then a number goes to a page", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    for (const name of ["Sign out", "Pause all (kill switch)", "Switch to dark theme", "Switch to light theme", "Run the jobs now", "Move the demo clock forward one day", "Reset the demo data", "Go to Fairness"]) await expect(page.getByRole("option", { name })).toBeVisible();
    await page.getByRole("option", { name: "Switch to dark theme" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.keyboard.press("g"); await page.keyboard.press("3");
    await expect(page).toHaveURL(/\/roles$/);
    await page.keyboard.press("g"); await page.keyboard.press("8");
    await expect(page).toHaveURL(/\/approvals$/);
    await page.keyboard.press("Meta+k");
    await page.getByRole("option", { name: "Reset the demo data" }).click();
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await toast(page, "Demo data reset.");
    await page.keyboard.press("Meta+k");
    await page.getByRole("option", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
  });

  test("the kill switch says what it stops, the top button becomes Turn it off, and an invite is refused while it is on", async ({ page }) => {
    await page.getByRole("button", { name: "Pause all" }).click();
    await page.getByRole("button", { name: "Pause all", exact: true }).last().click();
    await expect(page.getByText("Kill switch is on.")).toBeVisible();
    await expect(page.getByText(/No calendar invite is sent and no offer file is written/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn it off (kill switch)" })).toBeVisible();
    await page.goto("/interviews");
    await page.locator("[role=row]").nth(1).click();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Send the calendar invite" }).click();
    await toast(page, /Not sent\. The kill switch is on/);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Turn it off (kill switch)" }).click();
    await expect(page.getByText("Kill switch is on.")).toHaveCount(0);
  });

  test("on a phone, Pause all and Sign out are reachable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Pause all" })).toBeVisible();
    await page.getByRole("button", { name: "Pause all" }).click();
    await expect(page.getByRole("heading", { name: "Pause all sending?" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
  });

  test("signing in lands on the page that was asked for", async ({ page }) => {
    await signOut(page);
    await page.goto("/offers");
    await page.waitForURL(/\/login\?next=%2Foffers/);
    await page.getByLabel("Email").fill("owner@example.test");
    await page.getByLabel("Password").fill("demo-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/offers$/);
    await signOut(page);
    await page.goto("/login?next=https://example.com/steal");
    await page.getByLabel("Email").fill("owner@example.test");
    await page.getByLabel("Password").fill("demo-password-1");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/localhost:\d+\/$/); // an address on another site is ignored
  });

  test("Add applicants: a bad email blocks Add, an empty CSV is an error and a good one is added, a stray file drop does not leave the app", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Add applicants" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Kay Zed");
    await page.getByLabel("Email (optional)").fill("not-an-email");
    await page.getByLabel("Resume text").fill("I handled customer support tickets for four years and wrote help articles daily with calm replies.");
    await expect(page.getByRole("button", { name: "Add applicant", exact: true })).toBeDisabled();
    await page.getByLabel("Email (optional)").fill("kay@mail.example.test");
    await expect(page.getByRole("button", { name: "Add applicant", exact: true })).toBeEnabled();
    await page.getByRole("radio", { name: "CSV" }).click();
    await page.locator("input[type=file]").setInputFiles({ name: "empty.csv", mimeType: "text/csv", buffer: Buffer.from("") });
    await toast(page, /The file has no applicant rows/);
    await expect(page.locator("[data-sonner-toast]").filter({ hasText: "0 added" })).toHaveCount(0);
    const row = 'name,email,role,resume_text\nIvo Barrow,ivo@mail.example.test,support,"Customer Support Specialist, Acme Co, 2020 to 2026. Wrote replies to customer emails every day and trained 3 colleagues. Ran the helpdesk ticket queue."\n';
    await page.locator("input[type=file]").setInputFiles({ name: "people.csv", mimeType: "text/csv", buffer: Buffer.from(row) });
    await toast(page, /1 added/);
    await page.goto("/candidates");
    const prevented = await page.evaluate(() => { const dt = new DataTransfer(); dt.items.add(new File(["x"], "x.txt")); const ev = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }); document.body.dispatchEvent(ev); return ev.defaultPrevented; });
    expect(prevented).toBe(true);
  });

  test("the ATS and the mailbox say so when nothing new came, instead of a success tick", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Add applicants" }).click();
    await page.getByRole("radio", { name: "Your ATS" }).click();
    await page.getByRole("button", { name: "Read from the ATS now" }).click();
    await toast(page, /Nothing new came from the ATS/);
  });

  test("showing an identity is written to the audit log once, however often the page refreshes", async ({ page }) => {
    const id = await appId(page, "shortlisted");
    await page.goto(`/candidates/${id}`);
    await page.getByRole("button", { name: "Blind view on" }).click();
    await expect(page.getByRole("button", { name: "Identity shown" })).toBeVisible();
    for (let i = 0; i < 2; i++) { await call(page, "/demo/advance", { hours: 1 }); await page.waitForTimeout(1600); }
    const log = await json(await page.request.get("/api/audit?limit=300"));
    expect((log as unknown as { action: string; target: string }[]).filter((e) => e.action === "identity.revealed" && e.target === `application:${id}`)).toHaveLength(1);
  });

  test("a time the server stored is shown in the browser's own clock, not hours off", async ({ page }) => {
    await page.goto("/fairness");
    await page.getByRole("button", { name: "Run the report" }).click();
    await expect(page.getByText(/Saved (just now|\d+ min ago)/)).toBeVisible();
    await expect(page.getByText(/Saved \d+ h ago/)).toHaveCount(0);
  });

  test("a table row can be opened with a button, so a tap works as well as Enter", async ({ page }) => {
    await page.goto("/candidates");
    await page.getByRole("button", { name: /^Open Yarrow Mirabeau/ }).click();
    await expect(page).toHaveURL(/\/candidates\/\d+$/);
    await page.goto("/interviews");
    await page.getByRole("button", { name: /^Open the interview with / }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.goto("/audit");
    await page.getByRole("button", { name: /^Open entry / }).first().click();
    await expect(page.getByRole("dialog").getByText(/did this/)).toBeVisible();
  });

  test("on a phone the candidate names and roles in the tables are still readable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const path of ["/candidates", "/interviews", "/audit"]) {
      await page.goto(path);
      const widths = await page.locator(".sx-table__row").first().locator(".sx-table__cell").evaluateAll((cells) => cells.map((c) => c.getBoundingClientRect().width));
      expect(Math.min(...widths), `${path} has a column squeezed to nothing: ${widths.join(", ")}`).toBeGreaterThan(40);
    }
  });

  test("the audit log speaks in words, and Check the chain answers", async ({ page }) => {
    await page.goto("/audit");
    await expect(page.getByRole("gridcell", { name: "Offer file written" }).first()).toBeVisible();
    await expect(page.getByText("offer.handed_off")).toHaveCount(0);
    await expect(page.getByText("application:31")).toHaveCount(0);
    await page.getByRole("button", { name: "Check the chain" }).click();
    await toast(page, /Chain intact: \d+ entries checked/);
  });

  test("the fairness tables stay inside a phone screen, an invalid group size blocks the run, and the owner can import labels", async ({ page }) => {
    await page.goto("/fairness");
    await page.getByRole("button", { name: "Run the report" }).click();
    await expect(page.getByText("Shortlisted from all applicants")).toBeVisible();
    await page.getByLabel("Smallest group to compare").fill("1");
    await expect(page.getByRole("button", { name: "Run the report" })).toBeDisabled();
    await page.getByLabel("Smallest group to compare").fill("10");
    await page.getByLabel("Labels, one per line").fill("A003,B\nA005,B\nZ999,B");
    await page.getByRole("button", { name: "Save the labels" }).click();
    await toast(page, /2 labels saved, 1 code was not found/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });

  test("an approval shows the terms next to its buttons, and you cannot decide your own request", async ({ page }) => {
    await page.goto("/approvals");
    await expect(page.getByText(/Terms as written by the hiring manager/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Reject", exact: true })).toBeDisabled();
  });

  test("declining someone closes their waiting offer: it shows as withdrawn and leaves the approvals", async ({ page }) => {
    const offer = (await json(await page.request.get("/api/offers"))) as unknown as { application_id: number; status: string }[];
    const waiting = offer.find((o) => o.status === "pending_approval")!;
    await page.goto(`/candidates/${waiting.application_id}`);
    await page.getByRole("button", { name: "Decline", exact: true }).click();
    await page.getByLabel(/Reason/).fill("Withdrew after the final round, took another job.");
    await page.getByRole("button", { name: "Move", exact: true }).click();
    await toast(page, "Moved to Declined.");
    await page.goto("/offers");
    await expect(page.getByText("withdrawn", { exact: true })).toBeVisible();
    await expect(page.getByText(/the person left the process, so no file is written/)).toBeVisible();
    await page.goto("/approvals");
    await expect(page.getByText("Waiting (0)")).toBeVisible();
    await expect(page.getByText(/Closed: the candidate left the process/)).toBeVisible();
  });

  test("marking someone hired starts their onboarding plan, a task can be added, and the ring shows real progress", async ({ page }) => {
    const hand = async (offerId: number, appr: number) => {
      await signOut(page); await login(page, "approver@example.test");
      await call(page, `/approvals/${appr}/decide`, { approve: true, note: "" });
      await signOut(page); await login(page);
      expect((await call(page, `/offers/${offerId}/hand-off`)).ok()).toBeTruthy();
    };
    const offers = (await json(await page.request.get("/api/offers"))) as unknown as { id: number; application_id: number; status: string; approval: { id: number } }[];
    const w = offers.find((o) => o.status === "pending_approval")!;
    await hand(w.id, w.approval.id);
    await page.goto(`/candidates/${w.application_id}`);
    await page.getByRole("button", { name: "Mark hired" }).click();
    await toast(page, /onboarding plan was made/);
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: /Lazlo Hartnell/ })).toBeVisible();
    await page.getByRole("button", { name: "Add a task" }).last().click();
    await page.getByLabel("Task", { exact: true }).fill("Visit the second site");
    await page.getByRole("button", { name: "Add task" }).click();
    await toast(page, "Task added.");
    await expect(page.getByText("Visit the second site")).toBeVisible();
    // the ring of the first block follows done over total, not full as soon as one task is ticked
    const card = page.locator(".sx-card", { hasText: /Lazlo Hartnell/ }).first();
    await card.locator("input[type=checkbox]").first().check();
    await expect(card.getByRole("meter").first()).toHaveAttribute("aria-valuenow", /^(1[0-9]|2[0-9]|3[0-9])$/);
    const ring = () => card.locator("circle.sx-gauge__bar").first().evaluate((c) => Number(c.getAttribute("stroke-dashoffset")) / (2 * Math.PI * Number(c.getAttribute("r"))));
    await expect.poll(ring).toBeLessThan(0.95); // the ring has drawn in, but is far from full
    expect(await ring()).toBeGreaterThan(0.5);
  });

  test("deleting personal data also takes the name out of the offer text", async ({ page }) => {
    const offers = (await json(await page.request.get("/api/offers"))) as unknown as { application_id: number; status: string; name: string }[];
    const done = offers.find((o) => o.status === "handed_off")!;
    await page.goto(`/candidates/${done.application_id}`);
    await page.getByRole("button", { name: "Delete personal data" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await toast(page, /Personal data deleted/);
    await page.goto("/offers");
    await page.locator("summary", { hasText: "The terms and the file text" }).first().click();
    await expect(page.getByText(done.name)).toHaveCount(0);
  });

  test("the plan an interview and draft an offer dialogs start from the app's own date and refuse a past day", async ({ page }) => {
    await call(page, "/demo/advance", { hours: 24 * 10 });
    const id = await appId(page, "shortlisted");
    await page.goto(`/candidates/${id}`);
    await page.getByRole("button", { name: "Plan an interview" }).click();
    const start = page.getByLabel(/Starts/);
    await expect(start).toHaveValue(/^2026-12-18T10:00$/); // the demo clock is at 11 Dec, so a week on
    await start.fill("2026-12-01T10:00");
    await expect(page.getByText("That day has already passed.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Plan it" })).toBeDisabled();
    await start.fill("2026-12-20T10:00");
    await expect(page.getByRole("button", { name: "Plan it" })).toBeEnabled();
    await page.keyboard.press("Escape");
    const ivs = (await json(await page.request.get("/api/interviews"))) as unknown as { application_id: number; status: string }[];
    await page.goto(`/candidates/${ivs.find((i) => i.status === "done")!.application_id}`);
    await page.getByRole("button", { name: "Draft an offer" }).click();
    await expect(page.getByLabel(/Planned start date/)).toHaveValue("2027-01-25");
    await page.getByLabel("Job title").fill("");
    await page.getByLabel("Terms, in your words").fill("Salary of 50000 a year, 40 hours a week, six month review.");
    await expect(page.getByRole("button", { name: "Draft offer" })).toBeDisabled();
  });

  test("a waiting applicant says it is waiting for the next run, not that a rubric is missing", async ({ page }) => {
    const r = await json(await call(page, "/applicants", { name: "Jo Fictional", role: "support", resume_text: "Customer support for five years. I answered customer emails with calm written replies and handled helpdesk tickets every week. More text here." }));
    await page.goto(`/candidates/${r.application_id}`);
    await expect(page.getByText(/Waiting for the next run/)).toBeVisible();
    await expect(page.getByText(/needs a locked rubric/)).toHaveCount(0);
  });

  test("Run now says what it did, and says so when there is nothing new", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run now" }).click();
    await toast(page, /1 new application read/);
    for (let i = 0; i < 3; i++) await call(page, "/demo/tick");
    await page.waitForTimeout(1300); // a button ignores a second click while it shows its processing and success states
    await page.getByRole("button", { name: "Run now" }).click();
    await toast(page, /Nothing new: every demo email has already arrived/);
  });

  test("a refused action keeps its dialog and the typed reason, and its button shows no success tick", async ({ page }) => {
    await page.route("**/api/applications/*/move", (r) => r.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: { message: "Refused for the test." } }) }));
    await page.goto(`/candidates/${await appId(page, "applied")}`);
    await page.getByRole("button", { name: "Shortlist", exact: true }).click();
    await toast(page, "Not moved | Refused for the test.".split(" | ")[1]!);
    await page.waitForTimeout(500);
    await expect(page.getByRole("button", { name: "Shortlist", exact: true })).not.toHaveAttribute("data-state", "success");
    await page.getByRole("button", { name: "Decline", exact: true }).click();
    await page.getByLabel(/Reason/).fill("The role needs written examples and none were shown.");
    await page.getByRole("button", { name: "Move", exact: true }).click();
    await page.waitForTimeout(900);
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByLabel(/Reason/)).toHaveValue("The role needs written examples and none were shown.");
    await expect(page.getByRole("button", { name: "Move", exact: true })).not.toHaveAttribute("data-state", "success");
  });

  test("a failed load shows an error with Try again, not an empty page or a skeleton for ever", async ({ page }) => {
    await page.route("**/api/roles", (r) => (r.request().method() === "GET" ? r.abort() : r.continue()));
    await page.route("**/api/settings", (r) => (r.request().method() === "GET" ? r.abort() : r.continue()));
    await page.goto("/");
    await expect(page.getByText("Could not load the roles")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" }).first()).toBeVisible();
    await expect(page.getByText("Could not read the mode.")).toBeVisible();
    await page.unroute("**/api/roles");
    await page.getByRole("button", { name: "Try again" }).last().click();
    await expect(page.getByRole("group", { name: "Hiring pipeline" })).toBeVisible();
    await expect(page.getByText("Could not load the roles")).toHaveCount(0);
  });

  test("after a new rubric version is locked, people already scored keep their score on screen and can be read again", async ({ page }) => {
    const id = await appId(page, "shortlisted");
    const before = await json(await page.request.get(`/api/applications/${id}`));
    const role = ((await json(await page.request.get("/api/roles"))) as unknown as { id: number; key: string }[]).find((r) => r.key === before.role.key)!;
    const v2 = await json(await call(page, `/roles/${role.id}/rubric`, {}));
    expect((await call(page, `/rubrics/${v2.id}/lock`)).ok()).toBeTruthy();
    await page.goto(`/candidates/${id}`);
    await expect(page.getByText(/Scored under version 1/)).toBeVisible();
    await expect(page.getByText("Not scored yet")).toHaveCount(0);
    await page.goto("/candidates");
    await expect(page.getByRole("gridcell", { name: before.score.total.toFixed(1) }).first()).toBeVisible();
    await page.goto(`/candidates/${id}`);
    await page.getByRole("button", { name: "Score again under version 2" }).click();
    await expect(page.getByText(/Scored under version 1/)).toHaveCount(0);
    await expect(page.getByText(/Rubric version 2/)).toBeVisible();
  });

  test("a new role is selected after it is created", async ({ page }) => {
    await page.goto("/roles");
    await page.getByRole("button", { name: "New role" }).click();
    await page.getByLabel("Title", { exact: true }).fill("Warehouse Lead");
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("tab", { name: "Warehouse Lead" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("No rubric yet")).toBeVisible();
  });

  test("two criteria with the same name are explained in words", async ({ page }) => {
    const r = await json(await call(page, "/roles", { title: "Warehouse Lead", description: "Runs the day shift." }));
    const rub = await json(await call(page, `/roles/${r.id}/rubric`, {}));
    const c = { id: "safety", name: "Safety", weight: 3, anchors: { "1": "Has seen it done.", "3": "Does it alone.", "5": "Teaches others." }, look_for: ["safety"] };
    await page.request.put(`/api/rubrics/${rub.id}`, { headers: { "x-slatehire": "1", "content-type": "application/json" }, data: { criteria: [c, c] } });
    await page.goto("/roles");
    await page.getByRole("tab", { name: "Warehouse Lead" }).click();
    await expect(page.getByText(/another criterion has the same name/).first()).toBeVisible();
    await expect(page.getByText(/is used twice/)).toHaveCount(0);
  });

  test("an interview with no scorecards says so instead of a table of nones", async ({ page }) => {
    await page.goto("/interviews");
    await page.getByRole("button", { name: /^Open the interview with Yarrow/ }).click();
    await expect(page.getByRole("dialog").getByText(/No scorecards yet \(0 of 2\)/)).toBeVisible();
    await expect(page.getByRole("dialog").getByText("out of 100 from 0")).toHaveCount(0);
  });

  test("an address that does not exist has a page with a way back", async ({ page }) => {
    await page.goto("/no-such-page");
    await expect(page.getByRole("heading", { name: "That page does not exist" })).toBeVisible();
    await page.getByRole("link", { name: "Back to the pipeline" }).click();
    await expect(page.getByRole("heading", { name: "Pipeline", exact: true })).toBeVisible();
  });

  test("a candidate that does not exist says so in words", async ({ page }) => {
    await page.goto("/candidates/99999");
    await expect(page.getByText("Could not find this candidate")).toBeVisible();
    await expect(page.getByText("No such application.")).toBeVisible();
  });

  test("counting numbers never show decimals on the way to a whole number, after load and after a reset", async ({ page }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { __c: { final: string; now: string }[][] };
      w.__c = [];
      window.setInterval(() => { w.__c.push([...document.querySelectorAll("span.sx-num")].filter((e) => e.querySelector(":scope > .sx-sr-only")).map((e) => ({ final: e.querySelector(":scope > .sx-sr-only")!.textContent ?? "", now: e.querySelector(":scope > [aria-hidden]")?.textContent ?? "" }))); }, 30);
    });
    const decimals = (t: string) => (t.match(/\.(\d+)/)?.[1] ?? "").length;
    const bad: string[] = [];
    const collect = () => page.evaluate(() => (window as unknown as { __c: { final: string; now: string }[][] }).__c);
    const check = (rows: { final: string; now: string }[][]) => rows.flat().forEach((c) => { if (decimals(c.now) > decimals(c.final)) bad.push(`${c.now} on the way to ${c.final}`); });
    await page.goto("/");
    await page.waitForTimeout(2200);
    const afterLoad = await collect();
    check(afterLoad);
    expect(afterLoad.flat().length).toBeGreaterThan(20); // the counters were really watched
    await page.evaluate(() => { (window as unknown as { __c: unknown[] }).__c = []; });
    await call(page, "/demo/reset");
    await page.waitForTimeout(2600);
    const afterReset = await collect();
    check(afterReset);
    await page.goto("/candidates/60");
    await page.waitForTimeout(2200);
    check(await collect());
    expect(bad).toEqual([]);
  });
});
