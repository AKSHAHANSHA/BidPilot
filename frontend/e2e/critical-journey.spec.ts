import { test, expect } from "@playwright/test";

/**
 * The critical journey a reviewer takes, against the real backend with the demo seeded:
 * sign in → land on the tender desk → open the company workspace and confirm evidence renders →
 * open and close the edit-profile modal → open a tender if one exists → sign out.
 *
 * It deliberately does not upload a PDF or run an analysis (those need the worker and cost tokens);
 * those paths are covered by the backend integration suite and the manual live run.
 */

const DEMO_EMAIL = "demo@fm-demo.ae";
const DEMO_PASSWORD = "bidpilot-demo-passphrase-1";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill(DEMO_EMAIL);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "+ New Tender" })).toBeVisible();
}

test("sign in, view company workspace, and sign out", async ({ page }) => {
  await signIn(page);

  // Company workspace: profile, completion, and the evidence table must render.
  await page.getByRole("link", { name: "Company Profile" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Profile completion")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  // Edit-profile modal opens pre-populated and closes with Escape (keyboard accessibility).
  await page.getByRole("button", { name: "Edit profile" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit company profile" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Legal name")).not.toHaveValue("");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Sign out returns to the auth screen.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("session survives a hard refresh", async ({ page }) => {
  await signIn(page);
  await page.reload();
  // The in-memory access token is gone; the app must silently refresh from the HttpOnly cookie.
  await expect(page.getByRole("button", { name: "+ New Tender" })).toBeVisible();
});

test("open a tender command center when one exists", async ({ page }) => {
  await signIn(page);
  const tenderLink = page.locator('a[href^="/tenders/"]').first();
  if ((await tenderLink.count()) === 0) {
    test.skip(true, "No tender seeded; upload + analysis is covered elsewhere.");
  }
  await tenderLink.click();
  // Either an analysis is present (readiness) or the empty state invites running one.
  await expect(
    page.getByText(/BID READINESS|No analysis yet|Processing/i).first(),
  ).toBeVisible();
});
