import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./demo-tests",
  timeout: 60000,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: process.env.GRAPHPILOT_DEMO_URL || "http://127.0.0.1:18080",
    channel: process.env.PLAYWRIGHT_CHANNEL,
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
