import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Self-contained release gate: a disposable account + uploaded archive
// exercise literal search -> exact immutable source -> pinned Ask -> bounded
// static impact against whatever isolated stack GRAPHPILOT_E2E_URL points at.
// The archive is built by a fixed Python stdlib helper; no source is executed.
const ZIP_HELPER = `import json,os,sys,zipfile
files=json.loads(os.environ["E2E_ZIP_FILES"])
with zipfile.ZipFile(sys.argv[1],"w") as archive:
    for path,text in files.items():
        archive.writestr(path,text)`;

const padding = Array.from({ length: 230 }, (_, i) => `# padding ${i + 1}`);
const SOURCES: Record<string, string> = {
  "deep.py":
    padding.join("\n") +
    "\ndef marker_target():\n" +
    '    headers = {"X-CSRF-Token": "*"}\n' + // line 232, column 17
    '    message = "Request origin is not allowed"\n' +
    '    diagnostic = "graph_queries"\n' +
    "    return headers, message, diagnostic\n",
  "use.py":
    "from deep import marker_target\n\n" +
    "def calls_marker():\n" +
    "    return marker_target()\n",
  "short.txt": 'data = "  padded literal  "\nonly short text\n',
};

function zipSources(): Buffer {
  const zipPath = join(mkdtempSync(join(tmpdir(), "gp-e2e-")), "sources.zip");
  execFileSync("python3", ["-c", ZIP_HELPER, zipPath], {
    env: { ...process.env, E2E_ZIP_FILES: JSON.stringify(SOURCES) },
  });
  return readFileSync(zipPath);
}

test("literal search, exact source, pinned Ask and impact on a disposable upload", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL || "http://127.0.0.1:5173").origin;
  const account = {
    name: "E2E evidence",
    email: `e2e-content-${randomUUID()}@graphpilot.invalid`,
    password: "test-" + randomUUID() + "-long-password",
  };
  const registered = await page.request.post("/api/auth/register", {
    data: account,
    headers: { Origin: origin },
  });
  expect(registered.status()).toBe(201);
  const csrf = (await registered.json()).csrf;
  const upload = await page.request.post("/api/repositories/upload", {
    multipart: {
      file: {
        name: "e2e-evidence.zip",
        mimeType: "application/zip",
        buffer: zipSources(),
      },
      branch: "e2e",
    },
    headers: { "X-CSRF-Token": csrf, Origin: origin },
  });
  expect(upload.status()).toBe(201);
  const repositoryId = (await upload.json()).repository.id;
  const base = `/repositories/${repositoryId}`;
  await expect
    .poll(
      async () => (await page.request.get(`/api${base}`)).json().then((r) => r.status),
      { timeout: 90000 },
    )
    .toBe("ready");
  const repository = await (await page.request.get(`/api${base}`)).json();
  const snapshotId = repository.snapshot_id;
  expect(snapshotId).toBeTruthy();

  await page.goto(`${base}/code?mode=content`);
  await expect(
    page.getByRole("combobox", { name: "Search", exact: true }),
  ).toHaveValue("content");

  // A delayed scan response must surface a real loading state; a mocked
  // partial scan must surface the incomplete notice. One handler, flag-driven.
  let delayResponses = false;
  let mockedScan: object | null = null;
  await page.route("**/search/content*", async (route) => {
    if (delayResponses) await new Promise((resolve) => setTimeout(resolve, 400));
    if (mockedScan) {
      await route.fulfill({ json: mockedScan });
      return;
    }
    await route.continue();
  });
  delayResponses = true;
  await page.getByLabel("Search source text").fill("X-CSRF-Token");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await expect(page.getByText("Scanning retained source")).toBeVisible();
  delayResponses = false;

  const matchRow = page.getByRole("button", { name: /deep\.py:232:17/ });
  await expect(matchRow).toBeVisible();
  await expect(page.locator(".canvas-footnote")).toContainText(
    repository.commit_sha.slice(0, 8),
  );

  // The same mode keeps raw whitespace verbatim and reports an honest empty state.
  await page.getByLabel("Search source text").fill("  padded literal  ");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /short\.txt:1:9/ }),
  ).toBeVisible();
  await page.getByLabel("Search source text").fill("e2e-never-present");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();

  // A partial scan must show the incomplete notice even with zero results.
  mockedScan = {
    results: [],
    returned: 0,
    limit: 50,
    total: null,
    scan_complete: false,
    truncated: true,
    has_more: true,
    completion_reason: "time_budget",
    scan: {
      files_scanned: 1,
      files_skipped: 0,
      skip_reasons: {},
      bytes_scanned: 2048,
      elapsed_ms: 1501,
      manifest_entries: 3,
      manifest_incomplete: false,
    },
    graph_queries: 1,
    scope: {
      branch: repository.branch,
      snapshot_id: snapshotId,
      commit: repository.commit_sha,
      historical: false,
      manifest: "File nodes in the pinned graph only",
      case_sensitive: true,
      filters: { path: null, suffix: null },
    },
  };
  await page.getByLabel("Search source text").fill("e2e-partial-probe");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await expect(page.locator(".notice").first()).toContainText("Scan incomplete");
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();
  mockedScan = null;

  // Keyboard: the match row is a real button — focusable and Enter-activated.
  await page.getByLabel("Search source text").fill("X-CSRF-Token");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await matchRow.focus();
  await expect(matchRow).toBeFocused();
  await page.keyboard.press("Enter");
  const evidencePanel = page.getByRole("complementary", { name: "Node details" });
  await expect(
    evidencePanel.getByText("Source evidence", { exact: true }),
  ).toBeVisible();
  await expect(
    evidencePanel.getByText('headers = {"X-CSRF-Token": "*"}', { exact: false }),
  ).toBeVisible();
  // Exact anchored source over HTTP carries the verified content hash.
  const pinnedHit = await (
    await page.request.get(`/api${base}/search/content`, {
      params: { q: "X-CSRF-Token", branch: repository.branch, revision: snapshotId },
    })
  ).json();
  const hit = pinnedHit.results[0];
  expect(pinnedHit.scope.snapshot_id).toBe(snapshotId);
  expect(pinnedHit.scope.branch).toBe("e2e");
  expect(hit.line).toBe(232);
  const evidence = await (
    await page.request.get(`/api${base}/evidence/${hit.node_id}`, {
      params: {
        around: hit.line,
        column: hit.column,
        end_column: hit.end_column,
        branch: repository.branch,
        revision: snapshotId,
      },
    })
  ).json();
  expect(evidence.content).toContain("X-CSRF-Token");
  expect(evidence.content_hash).toMatch(/^[0-9a-f]{64}$/);
  expect(evidence.snapshot_id).toBe(snapshotId);

  // Symbol mode stays intact.
  await page.getByRole("combobox", { name: "Search", exact: true }).selectOption("symbols");
  await page.getByLabel("Search graph").fill("marker_target");
  await page.getByRole("button", { name: "Search symbols", exact: true }).click();
  await page.getByText("Browse nodes with keyboard", { exact: false }).click();
  await expect(
    page.getByRole("button", { name: /marker_target Function/ }),
  ).toBeVisible();

  // Pinned Ask: the match row hands its exact span to Ask on this snapshot.
  await page.getByRole("combobox", { name: "Search", exact: true }).selectOption("content");
  await page.getByLabel("Search source text").fill("X-CSRF-Token");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await page
    .locator(".match-list li")
    .filter({ hasText: "deep.py:232:17" })
    .getByRole("link", { name: /Ask/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`pin=${hit.node_id}`));
  await expect(page).toHaveURL(new RegExp(`revision=${snapshotId}`));
  await expect(page.getByText(/Source pinned · line 232/)).toBeVisible();
  const context = await (
    await page.request.post(`/api${base}/context`, {
      params: { branch: repository.branch, revision: snapshotId },
      data: {
        question: "What does this source do?",
        source: {
          node_id: hit.node_id,
          around: hit.line,
          column: hit.column,
          end_column: hit.end_column,
        },
      },
      headers: { "X-CSRF-Token": csrf, Origin: origin },
    })
  ).json();
  expect(context.snapshot_id).toBe(snapshotId);
  const pinnedCitation = context.evidence.find((c) => c.pinned);
  expect(pinnedCitation).toBeTruthy();
  expect(pinnedCitation.content).toContain("X-CSRF-Token");
  expect(pinnedCitation.content_hash).toMatch(/^[0-9a-f]{64}$/);
  await page.getByLabel("Ask about this repository").fill("What does this source do?");
  await page.getByRole("button", { name: "Ask GraphPilot", exact: true }).click();
  await expect(page.locator(".citations").first()).toContainText("deep.py");
  await expect(page.locator(".citations").first()).toContainText("pinned");

  // Trace dependencies: the real CALLS edge surfaces the caller.
  await page.goto(`${base}/impact`);
  await page.getByLabel("Find a file or function").fill("marker_target");
  await page.getByRole("button", { name: /marker_target/ }).click();
  await expect(page.getByRole("cell", { name: "calls_marker" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "1", exact: true })).toBeVisible();

  // Mobile: no horizontal overflow on the evidence workflow.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}/code?mode=content`);
  await page.getByLabel("Search source text").fill("X-CSRF-Token");
  await page.getByRole("button", { name: "Search content", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /deep\.py:232:17/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
