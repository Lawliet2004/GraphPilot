import { test, expect } from "@playwright/test";
import { randomBytes, randomUUID } from "node:crypto";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";

test("recorded CI log fixture: real archive, browser evidence, download and responsive layout", async ({
  browser,
}) => {
  const run = randomBytes(6).toString("hex");
  const email = `fixture-${run}@graphpilot.invalid`;
  const password = "test-" + randomUUID();
  const children: ChildProcess[] = [];
  for (const port of [8001, 5174]) {
    await new Promise<void>((resolve, reject) => {
      const probe = createServer();
      probe.once("error", () =>
        reject(
          new Error(
            `Fixture port ${port} is already in use; stop the previous fixture server before testing.`,
          ),
        ),
      );
      probe.listen(port, "127.0.0.1", () =>
        probe.close((error) => (error ? reject(error) : resolve())),
      );
    });
  }
  const stop = async () => {
    for (const child of children)
      if (child.pid && child.exitCode === null) {
        try {
          process.kill(-child.pid, "SIGTERM");
        } catch {
          /* already stopped */
        }
        await Promise.race([
          new Promise<void>((resolve) => child.once("exit", () => resolve())),
          new Promise<void>((resolve) => setTimeout(resolve, 3000)),
        ]);
      }
  };
  try {
    const fixture = JSON.parse(
      execFileSync(
        "uv",
        ["run", "python", "-m", "scripts.artifact_browser", "seed", run],
        {
          input: JSON.stringify({ email, password }),
          encoding: "utf8",
          stdio: ["pipe", "pipe", "pipe"],
        },
      ),
    );
    children.push(
      spawn(
        "uv",
        ["run", "python", "-m", "scripts.artifact_browser", "serve", run],
        { stdio: "ignore", detached: true },
      ),
    );
    children.push(
      spawn(
        "uv",
        ["run", "python", "-m", "scripts.artifact_browser", "worker", run],
        { stdio: "ignore", detached: true },
      ),
    );
    children.push(
      spawn("npm", ["--prefix", "app", "run", "dev", "--", "--port", "5174"], {
        env: { ...process.env, GP_API_PROXY: "http://127.0.0.1:8001" },
        stdio: "ignore",
        detached: true,
      }),
    );
    await expect
      .poll(async () => {
        try {
          return (await fetch("http://127.0.0.1:8001/api/health/ready")).status;
        } catch {
          return 0;
        }
      })
      .toBe(200);
    await expect
      .poll(async () => {
        try {
          return (await fetch("http://127.0.0.1:5174/")).status;
        } catch {
          return 0;
        }
      })
      .toBe(200);
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:5174",
      viewport: { width: 1440, height: 1000 },
    });
    try {
      const page = await context.newPage();
      page.setDefaultTimeout(15000);
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto("/login");
      await page.getByLabel("Email address").fill(email);
      await page.getByLabel("Password", { exact: true }).fill(password);
      await page.getByRole("button", { name: "Log in", exact: true }).click();
      await expect(page).toHaveURL("/workspace");
      await expect(
        page.getByRole("link", { name: /Recorded test run #1/ }),
      ).toBeVisible();
      await page.goto(`/repositories/${fixture.repository_id}/context`);
      await page
        .getByLabel("Ask about this repository")
        .fill("Investigate pytest");
      await page
        .getByRole("button", { name: "Ask GraphPilot", exact: true })
        .click();
      await expect(
        page.getByText(/Add or update your own model credentials in Settings/),
      ).toBeVisible();
      await page.goto("/workspace");
      await expect(
        page.getByRole("link", { name: /Investigate pytest/ }),
      ).toBeVisible();
      await page.screenshot({
        path: ".impeccable/review/workspace-recent-desktop.png",
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
        path: ".impeccable/review/workspace-recent-mobile.png",
        fullPage: true,
        animations: "disabled",
      });
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.goto(`/repositories/${fixture.repository_id}/history`);
      await page
        .getByRole("link", { name: "CI log: pytest fixture", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "CI log: pytest fixture",
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.locator(".code-block")).toContainText(
        "FAILED test_checkout service.py:12",
      );
      await expect(page.locator(".code-block")).toContainText("[REDACTED]");
      await expect(page.locator("body")).not.toContainText(
        "fixture-secret-never-visible",
      );
      const pending = page.waitForEvent("download");
      await page
        .getByRole("link", { name: "Download redacted log", exact: true })
        .click();
      const download = await pending;
      expect(download.suggestedFilename()).toBe(
        `ci-log-${fixture.artifact_id}.txt`,
      );
      const stream = await download.createReadStream();
      const chunks: Buffer[] = [];
      for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
      const text = Buffer.concat(chunks).toString();
      expect(text).toContain("FAILED test_checkout");
      expect(text).not.toContain("fixture-secret-never-visible");
      const logURL = page.url();
      await page
        .getByRole("link", { name: "Administration", exact: true })
        .click();
      await page
        .getByRole("button", { name: "configuration", exact: true })
        .click();
      await page
        .getByLabel("New log downloads per sync", { exact: true })
        .fill("0");
      await page
        .getByLabel("Retain new log archives (days)", { exact: true })
        .fill("1");
      await page
        .getByRole("button", { name: "Save log policy", exact: true })
        .click();
      await expect(page.getByRole("status")).toContainText("Log policy saved");
      expect(
        (await (await page.request.get("/api/admin/config")).json()).values
          .max_log_downloads,
      ).toBe(0);
      await page.screenshot({
        path: ".impeccable/review/admin-config-desktop.png",
        fullPage: true,
        animations: "disabled",
      });
      await page.goto(logURL);
      await expect(page.locator(".plot-coverage")).toContainText("6 of 6");
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await page.screenshot({
        path: ".impeccable/review/ci-log-desktop.png",
        fullPage: true,
        animations: "disabled",
      });
      await page.setViewportSize({ width: 390, height: 844 });
      await page
        .getByRole("button", { name: "View source", exact: true })
        .click();
      await expect(page.locator("#source-panel")).toBeFocused();
      await expect(
        page.getByRole("heading", {
          name: "CI log: pytest fixture",
          exact: true,
        }),
      ).toBeInViewport();
      await page.screenshot({
        path: ".impeccable/review/ci-log-mobile-source.png",
        animations: "disabled",
      });
      await page.evaluate(() =>
        window.scrollTo({ top: 0, behavior: "instant" }),
      );
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await page.screenshot({
        path: ".impeccable/review/ci-log-mobile.png",
        fullPage: true,
        animations: "disabled",
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      expect(errors).toEqual([]);
      await page.goto(`/repositories/${fixture.repository_id}/overview`);
      await page.getByText("Remove repository", { exact: true }).click();
      await page
        .getByLabel("Type Recorded CI log fixture to confirm removal")
        .fill("Recorded CI log fixture");
      await expect(
        page.getByRole("link", { name: "Skip to content", exact: true }),
      ).not.toBeInViewport();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      await page.evaluate(() =>
        window.scrollTo({ top: 0, behavior: "instant" }),
      );
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await page.screenshot({
        path: ".impeccable/review/repository-removal-mobile.png",
        fullPage: true,
        animations: "disabled",
      });
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.evaluate(() =>
        window.scrollTo({ top: 0, behavior: "instant" }),
      );
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await page.screenshot({
        path: ".impeccable/review/repository-removal-desktop.png",
        fullPage: true,
        animations: "disabled",
      });
      await page
        .getByRole("button", {
          name: "Remove repository and stored data",
          exact: true,
        })
        .click();
      await expect(page).toHaveURL("/workspace");
      await expect
        .poll(async () => {
          const audit = await (
            await page.request.get("/api/admin/audit")
          ).json();
          return audit.some(
            (event: { action: string; target: string }) =>
              event.action === "repository.removed" &&
              event.target === fixture.repository_id,
          );
        })
        .toBeTruthy();
      expect(
        (
          await page.request.get(
            `/api/repositories/${fixture.repository_id}/graph`,
          )
        ).status(),
      ).toBe(404);
    } finally {
      await context.close();
    }
  } finally {
    await stop();
    execFileSync(
      "uv",
      ["run", "python", "-m", "scripts.artifact_browser", "cleanup", run],
      { stdio: "pipe" },
    );
  }
});
