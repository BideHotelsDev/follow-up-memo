import { defineConfig, devices } from "@playwright/test"

// Runs against the app served by the API with the mock services (see README "With the mock services"): CI starts
// them; locally run pnpm dev:mocks and pnpm dev:api:mock with WEB_DIST_DIR set, or pnpm dev:web.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5175",
    trace: "retain-on-failure",
    // A fake microphone (a tone) for the Wispr Flow dictation test.
    launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
})
