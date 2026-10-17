import { test, expect } from "@playwright/test";

test("public landing renders without JavaScript errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Code makes more sense. Connected." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create workspace", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile landing fits and login is usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByLabel("Email address")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("anonymous admin access redirects to login", async ({ page }) => {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/login(?:\?|$)/);
  await expect(page.getByLabel("Email address")).toBeVisible();
});
