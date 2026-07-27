import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end critical-journey test.
 *
 * Prerequisites (the test drives the real app, it does not mock the backend):
 *   1. Backend running on http://127.0.0.1:8000  (make api)
 *   2. Worker running                            (make worker)
 *   3. Demo seeded                               (make seed)
 *   4. Chromium installed once                   (npx playwright install chromium)
 *
 * Then:  npm run e2e
 *
 * Playwright starts the Vite dev server itself (see `webServer`); the backend and worker are the
 * developer's responsibility because they own the database and job queue.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
