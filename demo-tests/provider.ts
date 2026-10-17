import type { Page } from "@playwright/test";

// A fresh browser must acknowledge GitHub's development-port notice once.
// This is provider navigation, before GraphPilot's own authentication.
export async function prepareCodespaces(page: Page, baseURL?: string) {
  if (!baseURL || !new URL(baseURL).hostname.endsWith(".app.github.dev")) return;
  await page.goto("/");
  const notice = page.getByRole("heading", {
    name: "You are about to access a development port served by someone's codespace",
    exact: true,
  });
  if (await notice.isVisible()) {
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.locator("#root").waitFor();
  }
}
