import { test, expect } from "@playwright/test";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";

test.use({ reducedMotion: "reduce" });

test("real browser CLI approval, signup return, scoped access and revocation", async ({
  page,
  baseURL,
}) => {
  const origin = baseURL!;
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  const started = await page.request.post("/api/cli/device", {
    headers: { Origin: origin },
    data: { challenge, write: true, name: "Browser CLI verification" },
  });
  expect(started.status()).toBe(201);
  const grant = await started.json();
  const code = grant.user_code.replaceAll("-", "");
  await page.goto("/cli/authorize?code=" + code);
  await page.getByRole("link", { name: "Sign in to GraphPilot" }).click();
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Your name").fill("CLI verification user");
  await page
    .getByLabel("Email address")
    .fill(`cli-${randomUUID()}@graphpilot.invalid`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("test-" + randomUUID());
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByRole("heading", { name: "Approve CLI access" }),
  ).toBeVisible();
  await expect(page.getByText("Browser CLI verification")).toBeVisible();
  await expect(
    page.getByText(
      "Connect repositories, upload source, request indexing or history sync, ask questions, and remove repositories you own.",
    ),
  ).toBeVisible();
  await mkdir(".data/professional-demo", { recursive: true });
  await page.screenshot({
    path: ".data/professional-demo/cli-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: ".data/professional-demo/cli-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Approve CLI", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("CLI approved");
  const polled = await page.request.post("/api/cli/device/poll", {
    headers: { Origin: origin },
    data: { device_code: grant.device_code, verifier },
  });
  expect(polled.status()).toBe(200);
  const access = await polled.json();
  const headers = { Authorization: "Bearer " + access.token };
  expect(
    (await page.request.get("/api/repositories", { headers })).status(),
  ).toBe(200);
  expect(
    (await page.request.get("/api/admin/users", { headers })).status(),
  ).toBe(403);
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "CLI & agent access" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Revoked", exact: true }),
  ).toBeDisabled();
  expect(
    (await page.request.get("/api/repositories", { headers })).status(),
  ).toBe(401);
});

test("GitHub picker handles selected private repositories and provider denial (mocked provider UI)", async ({
  page,
  baseURL,
}) => {
  await mkdir(".data/professional-demo", { recursive: true });
  const registered = await page.request.post("/api/auth/register", {
    headers: { Origin: baseURL! },
    data: {
      name: "GitHub UI verification",
      email: `github-ui-${randomUUID()}@graphpilot.invalid`,
      password: "test-" + randomUUID(),
    },
  });
  expect(registered.status()).toBe(201);
  await page.route("**/api/integrations/github", (route) =>
    route.fulfill({
      json: {
        configured: true,
        connected: true,
        login: "example-account",
        install_url:
          "https://github.com/apps/example-test-app/installations/new",
      },
    }),
  );
  await page.route("**/api/integrations/github/installations", (route) =>
    route.fulfill({ json: [{ id: 55, account: "example-account" }] }),
  );
  await page.route(
    "**/api/integrations/github/installations/55/repositories?*",
    (route) =>
      route.fulfill({
        json: {
          repositories: [
            {
              id: 808,
              full_name: "example-account/private-demo",
              private: true,
              default_branch: "main",
            },
          ],
          has_more: false,
        },
      }),
  );
  await page.route("**/api/integrations/github/repositories", (route) =>
    route.fulfill({
      status: 403,
      json: { detail: "GitHub access changed. Reconnect your account." },
    }),
  );
  await page.goto("/connect");
  await page.getByLabel("Authorized repository").selectOption("808");
  await expect(page.getByLabel("Authorized repository")).toContainText(
    "Private",
  );
  await page.screenshot({
    path: ".data/professional-demo/github-picker-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: ".data/professional-demo/github-picker-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Connect selected repository" })
    .click();
  await expect(page.getByRole("alert")).toContainText("GitHub access changed");
  await expect(
    page.getByRole("button", { name: "Connect selected repository" }),
  ).toBeEnabled();
});
