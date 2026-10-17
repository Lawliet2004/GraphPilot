import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";

test.use({ reducedMotion: "reduce" });

test("BYOK settings keep credentials private and support replace/remove", async ({
  page,
  baseURL,
}) => {
  const signup = await page.request.post("/api/auth/register", {
    headers: { Origin: baseURL! },
    data: {
      name: "BYOK verification",
      email: `byok-${randomUUID()}@graphpilot.invalid`,
      password: "fixture-" + randomUUID(),
    },
  });
  expect(signup.status()).toBe(201);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/settings");
  const section = page.locator("section.model-credentials");
  await expect(
    section.getByRole("heading", { name: "AI synthesis with your own key" }),
  ).toBeVisible();
  const status = await page.request.get("/api/model");
  expect(status.status()).toBe(200);
  if (!(await status.json()).byok_available) {
    await expect(section).toContainText("Graph search");
    await expect(section.getByLabel("API key", { exact: true })).toHaveCount(0);
    return;
  }
  const key = "fixture-personal-key-" + randomUUID();
  await expect(
    section.getByRole("button", { name: "Save credentials", exact: true }),
  ).toBeDisabled();
  await section.getByLabel("Model", { exact: true }).fill("openrouter/free");
  await section.getByLabel("API key", { exact: true }).fill(key);
  await section
    .getByRole("button", { name: "Save credentials", exact: true })
    .click();
  await expect(
    section.getByRole("button", { name: "Replace credentials" }),
  ).toBeVisible();
  await expect(section).toContainText("openrouter/free");
  await expect(section.getByLabel("API key", { exact: true })).toHaveCount(0);
  const saved = await page.request.get("/api/model");
  expect(await saved.text()).not.toContain(key);
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(key);

  if (process.env.GRAPHPILOT_BYOK_QA) {
    await mkdir(".impeccable/review", { recursive: true });
    await page.evaluate(() => {
      (document.activeElement as HTMLElement)?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: ".impeccable/review/byok-saved-desktop.png",
      fullPage: true,
      animations: "disabled",
    });
  }
  await section.getByRole("button", { name: "Replace credentials" }).click();
  await expect(section.getByLabel("API key", { exact: true })).toHaveValue("");
  await section
    .getByLabel("API key", { exact: true })
    .fill("unsent-fixture-key");
  await section.getByRole("button", { name: "Cancel", exact: true }).click();
  await section.getByRole("button", { name: "Replace credentials" }).click();
  await expect(section.getByLabel("API key", { exact: true })).toHaveValue("");
  await section.getByRole("button", { name: "Cancel", exact: true }).click();
  await section
    .getByRole("button", { name: "Remove key", exact: true })
    .click();
  await section
    .getByRole("button", { name: "Confirm removal", exact: true })
    .click();
  await expect(
    section.getByRole("button", { name: "Save credentials", exact: true }),
  ).toBeVisible();
  expect((await (await page.request.get("/api/model")).json()).configured).toBe(
    false,
  );
  await section.getByLabel("Model", { exact: true }).fill("openrouter/free");
  await section
    .getByLabel("API key", { exact: true })
    .fill("invalid key with whitespace");
  await section
    .getByRole("button", { name: "Save credentials", exact: true })
    .click();
  await expect(section.getByRole("alert")).toBeVisible();
  await expect(section.getByRole("alert")).not.toContainText(
    "invalid key with whitespace",
  );
  // Navigation discards any unsent secret rather than storing it in the browser.
  await page.goto("/workspace");
  await page.goto("/settings");
  await expect(section.getByLabel("API key", { exact: true })).toHaveValue("");
  if (process.env.GRAPHPILOT_BYOK_QA) {
    await page.screenshot({
      path: ".impeccable/review/byok-empty-desktop.png",
      fullPage: true,
      animations: "disabled",
    });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: ".impeccable/review/byok-empty-mobile.png",
      fullPage: true,
      animations: "disabled",
    });
  }
  expect(errors).toEqual([]);
});
