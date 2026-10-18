import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { prepareCodespaces } from "../demo-tests/provider";
const email = `e2e-${randomUUID()}@graphpilot.invalid`;
const password = "test-" + randomUUID() + "-long-password";
const screenshotDir = ".impeccable/review";

test.beforeEach(async ({ page, baseURL }) => {
  await prepareCodespaces(page, baseURL);
});

test("real repository journey, source evidence, settings, restrictions and responsive layouts", async ({
  page,
}) => {
  await mkdir(screenshotDir, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Code makes more sense. Connected." }),
  ).toBeVisible();
  await page.screenshot({
    path: screenshotDir + "/landing-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: screenshotDir + "/landing-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("link", { name: "Create workspace", exact: true })
    .click();
  await page.getByLabel("Your name").fill("E2E Developer");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/workspace");
  await expect(
    page.getByRole("heading", {
      name: "Every connection starts with a repository.",
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 834, height: 1112 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: screenshotDir + "/workspace-tablet.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.goto(`/repositories/${randomUUID()}`);
  await expect(page.getByRole("alert")).toContainText("Repository not found");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Repository not found");
  await page.goto("/workspace");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("link", { name: "Add repository" }).first().click();
  await page
    .getByLabel("Public GitHub repository URL")
    .fill("https://github.com/pallets/itsdangerous");
  await page.getByLabel("Branch", { exact: true }).fill("main");
  await page.getByRole("button", { name: "Connect & index" }).click();
  await expect(page).toHaveURL(/\/repositories\/[a-z0-9-]+$/);
  const repositoryURL = page.url();
  await expect(
    page.getByRole("status").filter({ hasText: "Indexing repository" }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page
      .getByRole("navigation", { name: "Repository navigation" })
      .getByRole("link"),
  ).toHaveCount(4);
  await page.getByRole("link", { name: "Graph", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /Interactive repository graph/ }),
  ).toBeVisible({ timeout: 90000 });
  const repositoryPath = new URL(repositoryURL).pathname;
  const mainSnapshot = await (
    await page.request.get("/api" + repositoryPath)
  ).json();
  await page.getByLabel("Search graph").fill("want_bytes");
  await page.getByRole("button", { name: "Search symbols" }).click();
  await page.getByText("Browse nodes with keyboard").click();
  await page
    .getByRole("button", { name: "want_bytes Function", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "want_bytes", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("def want_bytes", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open source on GitHub" }),
  ).toHaveAttribute(
    "href",
    /github.com\/pallets\/itsdangerous\/blob\/[a-f0-9]{40}\//,
  );
  await page.getByRole("button", { name: "Expand neighbors" }).click();
  await expect(page.getByText("200 nodes loaded")).not.toBeVisible();
  await page.screenshot({
    path: screenshotDir + "/desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "View source", exact: true }).click();
  await expect(page.locator("#source-panel")).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "want_bytes", exact: true }),
  ).toBeInViewport();
  await page.screenshot({
    path: screenshotDir + "/mobile-source.png",
    animations: "disabled",
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await page.screenshot({
    path: screenshotDir + "/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByLabel("Relationship type", { exact: true })
    .selectOption("CALLS");
  await page
    .getByRole("button", { name: "Expand neighbors", exact: true })
    .click();
  await expect(page.locator(".connection-entries")).toContainText("CALLS");
  await expect(page.locator(".connection-entries")).not.toContainText(
    "DEFINES",
  );
  await page.getByRole("link", { name: "Ask", exact: true }).click();
  await page
    .getByLabel("Ask about this repository")
    .fill("Find callers of want_bytes");
  await page.getByRole("button", { name: "Ask GraphPilot" }).click();
  await expect(
    page.getByText("Graph retrieval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Add or update your own model credentials in Settings", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.locator(".context-results")).toContainText("want_bytes");
  await page.getByRole("link", { name: "Graph", exact: true }).click();
  await page.getByText("Trace dependencies", { exact: true }).click();
  await page.getByLabel("Find a file or function").fill("want_bytes");
  await page
    .getByRole("button", { name: /want_bytes/ })
    .first()
    .click();
  await expect(
    page.getByRole("columnheader", { name: "Evidence classification" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Repository navigation" })
    .getByRole("link", { name: "History", exact: true })
    .click();
  await page.getByText("Index health", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Latest index checks" }),
  ).toBeVisible();
  await page.getByText("Branch & saved versions", { exact: true }).click();
  await page.getByText("Connect branch", { exact: true }).click();
  await page.getByLabel("Existing Git branch", { exact: true }).fill("stable");
  await page
    .getByRole("button", { name: "Connect & index branch", exact: true })
    .click();
  await expect(page.getByLabel("Branch", { exact: true })).toHaveValue(
    "stable",
  );
  await expect
    .poll(
      async () => {
        const response = await page.request.get(
          "/api" + repositoryPath + "?branch=stable",
        );
        return (await response.json()).status;
      },
      { timeout: 90000 },
    )
    .toBe("ready");
  const stableSnapshot = await (
    await page.request.get("/api" + repositoryPath + "?branch=stable")
  ).json();
  expect(stableSnapshot.commit_sha).not.toBe(mainSnapshot.commit_sha);
  expect(
    (await (await page.request.get("/api" + repositoryPath)).json())
      .snapshot_id,
  ).toBe(mainSnapshot.snapshot_id);
  await page.getByRole("link", { name: "Graph", exact: true }).click();
  await expect(page).toHaveURL(/branch=stable/);
  await expect(
    page
      .getByLabel("Snapshot", { exact: true })
      .locator("option", { hasText: stableSnapshot.commit_sha.slice(0, 8) }),
  ).toHaveCount(1);
  await page
    .getByLabel("Snapshot", { exact: true })
    .selectOption(stableSnapshot.snapshot_id);
  await expect(
    page.getByRole("button", { name: "Sync source", exact: true }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "Ask", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp("revision=" + stableSnapshot.snapshot_id),
  );
  await page.getByLabel("Ask about this repository").fill("Explain want_bytes");
  await page.getByRole("button", { name: "Ask GraphPilot" }).click();
  const evidenceLink = page
    .locator(".context-results a")
    .filter({ hasText: "want_bytes" })
    .first();
  await expect(evidenceLink).toHaveAttribute(
    "href",
    new RegExp("revision=" + stableSnapshot.snapshot_id),
  );
  await evidenceLink.click();
  await expect(
    page.getByRole("heading", { name: "want_bytes", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Branch", { exact: true })).toHaveValue(
    "stable",
  );
  await page
    .getByRole("button", { name: "Clear selected node", exact: true })
    .click();
  await expect(page).toHaveURL(
    new RegExp("revision=" + stableSnapshot.snapshot_id),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: screenshotDir + "/branch-snapshot-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: screenshotDir + "/branch-snapshot-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("Snapshot", { exact: true }).selectOption("");
  await expect(
    page.getByRole("button", { name: "Sync source", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Branch", { exact: true }).selectOption("main");
  await expect(page.getByLabel("Branch", { exact: true })).toHaveValue("main");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("E2E Updated");
  await page.getByLabel("dark", { exact: true }).check();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(
    page.getByRole("button", { name: "Saved", exact: true }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: screenshotDir + "/settings-dark.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("light", { exact: true }).check();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await page.goto("/admin");
  await expect(page).toHaveURL("/workspace");
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page).toHaveURL("/login");
  await page.goto(repositoryURL);
  await expect(page).toHaveURL("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Email or password is incorrect",
  );
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL("/workspace");
  await expect(
    page.getByRole("heading", { name: "itsdangerous", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("admin bootstrap, live role changes, membership grants and audit events", async ({
  page,
  playwright,
  baseURL,
}) => {
  page.setDefaultTimeout(15000);
  const { execFileSync } = await import("node:child_process");
  const adminEmail = `e2e-admin-${randomUUID()}@graphpilot.invalid`;
  const memberEmail = `e2e-member-${randomUUID()}@graphpilot.invalid`;
  const adminPassword = "admin-" + randomUUID() + "-long-password";
  execFileSync(
    "uv",
    [
      "run",
      "python",
      "-m",
      "api.cli",
      "create-admin",
      adminEmail,
      "--name",
      "E2E Administrator",
    ],
    {
      input: adminPassword + "\n" + adminPassword + "\n",
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  const memberBaseURL = baseURL || "http://127.0.0.1:5173";
  const memberOrigin = new URL(memberBaseURL).origin;
  const member = await playwright.request.newContext({
    baseURL: memberBaseURL,
    extraHTTPHeaders: { Origin: memberOrigin },
  });
  const registered = await member.post("/api/auth/register", {
    data: {
      name: "E2E Permission Subject",
      email: memberEmail,
      password: "member-" + randomUUID() + "-long-password",
    },
  });
  expect(registered.status()).toBe(201);
  const memberIdentity = await registered.json();
  expect((await member.get("/api/admin/users")).status()).toBe(403);
  await page.goto("/login");
  await page.getByLabel("Email address").fill(adminEmail);
  await page.getByLabel("Password", { exact: true }).fill(adminPassword);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL("/workspace");
  await page.getByRole("link", { name: "Administration", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace administration" }),
  ).toBeVisible();
  const role = page.getByLabel("Role for " + memberEmail, { exact: true });
  await role.selectOption("admin");
  await expect(role).toHaveValue("admin");
  await expect
    .poll(async () => (await member.get("/api/admin/users")).status())
    .toBe(200);
  await role.selectOption("user");
  await expect(role).toHaveValue("user");
  await expect
    .poll(async () => (await member.get("/api/admin/users")).status())
    .toBe(403);
  const fixtureArchive = execFileSync("uv", [
    "run",
    "python",
    "-c",
    "import io,zipfile,sys; b=io.BytesIO(); z=zipfile.ZipFile(b,'w'); z.writestr('fixture.py','def administration_fixture(): return 1\\n'); z.close(); sys.stdout.buffer.write(b.getvalue())",
  ]);
  const fixtureName = "admin-fixture-" + randomUUID().slice(0, 8);
  const connected = await member.post("/api/repositories/upload", {
    headers: { "X-CSRF-Token": memberIdentity.csrf },
    multipart: {
      file: {
        name: fixtureName + ".zip",
        mimeType: "application/zip",
        buffer: fixtureArchive,
      },
    },
  });
  expect(connected.status()).toBe(201);
  const fixtureId = (await connected.json()).repository.id;
  await expect
    .poll(
      async () =>
        (await (await member.get(`/api/repositories/${fixtureId}`)).json())
          .status,
    )
    .toBe("ready");
  const receivingEmail = `e2e-member-${randomUUID()}@graphpilot.invalid`;
  const receiving = await playwright.request.newContext({
    baseURL: memberBaseURL,
    extraHTTPHeaders: { Origin: memberOrigin },
  });
  const received = await receiving.post("/api/auth/register", {
    data: {
      name: "E2E ownership recipient",
      email: receivingEmail,
      password: "member-" + randomUUID(),
    },
  });
  expect(received.status()).toBe(201);
  expect(
    (await receiving.get(`/api/repositories/${fixtureId}/graph`)).status(),
  ).toBe(404);
  await page.getByRole("button", { name: "repositories", exact: true }).click();
  await page
    .getByRole("row")
    .filter({ hasText: fixtureName })
    .getByRole("button", { name: "Manage members", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Account", exact: true })
    .selectOption({ label: receivingEmail });
  await page.getByLabel("Permission", { exact: true }).selectOption("read");
  await page.getByRole("button", { name: "Grant access", exact: true }).click();
  await expect
    .poll(async () =>
      (await receiving.get(`/api/repositories/${fixtureId}/graph`)).status(),
    )
    .toBe(200);
  await page
    .locator(".member-row")
    .filter({ hasText: receivingEmail })
    .getByRole("button", { name: "Revoke", exact: true })
    .click();
  await expect
    .poll(async () =>
      (await receiving.get(`/api/repositories/${fixtureId}/graph`)).status(),
    )
    .toBe(404);
  await page
    .getByLabel("New owner", { exact: true })
    .selectOption({ label: receivingEmail });
  await page
    .getByLabel("Previous owner access", { exact: true })
    .selectOption("read");
  await page
    .getByRole("button", { name: "Transfer ownership", exact: true })
    .click();
  await expect(page.locator(".access-panel p strong")).toHaveText(
    receivingEmail,
  );
  await expect(
    page.getByRole("button", { name: "Transfer ownership", exact: true }),
  ).toBeDisabled();
  expect(
    (await (await receiving.get(`/api/repositories/${fixtureId}`)).json())
      .permission,
  ).toBe("owner");
  expect(
    (
      await member.post(`/api/repositories/${fixtureId}/jobs`, {
        headers: { "X-CSRF-Token": memberIdentity.csrf },
      })
    ).status(),
  ).toBe(403);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: screenshotDir + "/admin-access-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await receiving.dispose();
  await page.getByRole("button", { name: "jobs", exact: true }).click();
  await expect(
    page.getByRole("columnheader", { name: "Progress", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "audit", exact: true }).click();
  await expect(
    page.getByText("admin.account_update", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: screenshotDir + "/admin-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", { name: "System health", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Live database connectivity" }),
  ).toBeVisible();
  await expect(page.getByText("connected", { exact: true })).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "Worker observations", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/recent · (waiting|working)/).first(),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: screenshotDir + "/admin-health-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await member.dispose();
});
