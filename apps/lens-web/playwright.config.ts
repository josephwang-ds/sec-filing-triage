import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end checks against a real build.
 *
 * Against `next start`, not the dev server: the things being checked here --
 * static generation of both locales, the legacy redirects, the proxy's locale
 * negotiation -- behave differently in dev, and a test that passes only in dev
 * is not evidence about what ships.
 *
 * Fixture data, so the suite exercises both a fully populated company and a
 * sparse one. No test sends a question to a model provider: the Ask paths
 * covered here are configuration, validation and error states, all of which
 * resolve before any paid call would be made.
 */
const PORT = Number(process.env.LENS_E2E_PORT ?? 4320);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  // The widths the layout has to hold, all on Chromium. The phone projects
  // emulate a touch device at each end of the 375-430px range rather than
  // using a WebKit device profile: what is being tested here is the layout at
  // those widths, and pinning the suite to a second browser engine would make
  // it need a second browser download to run at all.
  projects: [
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 375, height: 812 },
        isMobile: false,
        hasTouch: true,
      },
    },
    {
      name: "mobile-wide",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 430, height: 932 },
        isMobile: false,
        hasTouch: true,
      },
    },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } },
    { name: "wide", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: `LENS_USE_FIXTURES=1 npm run build:fixtures && npx next start --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/zh`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
