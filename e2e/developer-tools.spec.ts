import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { prepareCodespaces } from "../demo-tests/provider";
const email = `e2e-tools-${randomUUID()}@graphpilot.invalid`;
const password = "test-" + randomUUID() + "-long-password";

test.beforeEach(async ({ page, baseURL }) => {
  await prepareCodespaces(page, baseURL);
});

test("developer tools builds copyable CLI commands and the palette navigates", async ({
  page,
}) => {
  page.setDefaultTimeout(20000);
  await page.goto("/");
  await page
    .getByRole("link", { name: "Create workspace", exact: true })
    .click();
  await page.getByLabel("Your name").fill("E2E Tools");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/workspace");

  await page
    .getByRole("link", { name: "CLI & MCP", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL("/tools");
  await expect(
    page.getByRole("heading", { name: "CLI & MCP." }),
  ).toBeVisible();
  for (const name of ["Code questions", "Cloud Runner", "Daily Git"]) {
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  }
  await expect(page.getByText("Backend API")).toBeVisible();
  await expect(page.getByText(/login --server 'http/)).toBeVisible();
  await expect(page.getByText("Connect a repository first.")).toBeVisible();

  await page.goto("/connect");
  await page
    .getByLabel("Public GitHub repository URL")
    .fill("https://github.com/pallets/itsdangerous");
  await page.getByLabel("Branch", { exact: true }).fill("main");
  await page.getByRole("button", { name: "Connect & index" }).click();
  await expect(page).toHaveURL(/\/repositories\/[a-z0-9-]+$/);
  const repoId = new URL(page.url()).pathname.split("/").pop()!;

  await page.goto("/tools");
  const codeQuestions = page.locator("section.tool-group").filter({
    has: page.getByRole("heading", { name: "Code questions" }),
  });
  await codeQuestions
    .getByRole("textbox", { name: "Question" })
    .fill("Who calls checkout?");
  const command = codeQuestions.locator(".command-block code");
  await expect(command).toContainText(
    `./scripts/graphpilot ask '${repoId}' 'Who calls checkout?'`,
  );
  await codeQuestions.getByLabel("Task").selectOption("jobs");
  await expect(command).toContainText(`jobs list '${repoId}'`);
  await codeQuestions.getByLabel("Task").selectOption("cancel");
  await codeQuestions
    .getByLabel("Job ID")
    .fill("123e4567-e89b-42d3-a456-426614174000");
  await expect(command).toContainText(
    "jobs cancel '123e4567-e89b-42d3-a456-426614174000'",
  );

  const runner = page.locator("section.tool-group").filter({
    has: page.getByRole("heading", { name: "Cloud Runner" }),
  });
  const runnerCommand = runner.locator(".command-block code");
  await runner.getByLabel("Task").selectOption("configure");
  await runner.getByRole("textbox", { name: "Profile" }).fill("daily");
  await runner.getByLabel("Codespace name").fill("graphpilot-dev");
  await expect(runnerCommand).toContainText(
    "runner configure 'daily' --codespace 'graphpilot-dev'",
  );
  await runner.getByLabel("Task").selectOption("logs");
  await runner.getByRole("combobox", { name: "Service" }).selectOption("api");
  await expect(runnerCommand).toContainText(
    "runner logs 'daily' --service 'api' --lines 200",
  );

  const git = page.locator("section.tool-group").filter({
    has: page.getByRole("heading", { name: "Daily Git" }),
  });
  const gitCommand = git.locator(".command-block code");
  await expect(gitCommand).toContainText("git daily --path '.'");
  await git.getByLabel("Task").selectOption("stage");
  await git
    .getByRole("textbox", { name: "Files" })
    .fill("app/src/It's live.tsx\ndocs/notes, draft.md");
  await expect(gitCommand).toContainText(
    "git stage 'app/src/It'\\''s live.tsx' 'docs/notes, draft.md' --path '.'",
  );
  await git.getByLabel("Task").selectOption("commit");
  await git
    .getByRole("textbox", { name: "Commit message" })
    .fill("Sort graph edges by line");
  await expect(gitCommand).toContainText(
    "git commit --message 'Sort graph edges by line' --path '.'",
  );

  await page
    .context()
    .grantPermissions(["clipboard-read", "clipboard-write"])
    .catch(() => {});
  await git.getByRole("button", { name: "Copy", exact: true }).click();
  await expect(git.getByRole("button", { name: "Copied" })).toBeVisible();

  await page.getByRole("button", { name: "Search and commands" }).click();
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette
    .getByLabel("Search repositories and commands")
    .fill("itsdangerous");
  await expect(palette.getByRole("option")).toHaveCount(3);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/repositories\/[a-z0-9-]+$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await expect(
    page.getByRole("navigation", { name: "Repository navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // Drain this spec's own external indexing job before exiting: the shared
  // worker is serial, so a still-running GitHub ingestion here delays the
  // next spec's repository. Bounded by a real remote-ingestion deadline;
  // a stuck or failed job surfaces instead of being hidden.
  await expect
    .poll(
      async () =>
        (await page.request.get(`/api/repositories/${repoId}`)).json().then(
          (r) => r.status,
        ),
      { timeout: 180000 },
    )
    .toBe("ready");
});
