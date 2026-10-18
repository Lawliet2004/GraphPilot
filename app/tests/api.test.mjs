import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(
  new URL("../src/lib/api.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
const { api, ApiError } = await import(
  "data:text/javascript;base64," + Buffer.from(compiled).toString("base64")
);
globalThis.document = { cookie: "gp_csrf=verification-csrf" };

const availability =
  /server|backend|connection|unavailable|connect|retry|try again/i;

test("successful requests retain session and CSRF headers", async () => {
  let request;
  globalThis.fetch = async (path, options) => {
    request = { path, ...options };
    return Response.json({ ready: true });
  };
  assert.deepEqual(await api("/health/ready"), { ready: true });
  assert.equal(request.path, "/api/health/ready");
  assert.equal(request.credentials, "include");
  assert.equal(
    new Headers(request.headers).get("X-CSRF-Token"),
    "verification-csrf",
  );
});

test("readable API details and field validation survive transport handling", async () => {
  for (const [status, detail, expected] of [
    [401, "Please log in to continue", "Please log in to continue"],
    [422, [{ msg: "Value error, Choose a branch" }], "Choose a branch"],
  ]) {
    globalThis.fetch = async () => Response.json({ detail }, { status });
    await assert.rejects(api("/repositories"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.equal(error.message, expected);
      return true;
    });
  }
});

test("gateway failures explain availability without exposing response bodies", async () => {
  for (const status of [502, 503, 504]) {
    globalThis.fetch = async () =>
      new Response("<html>private-gateway-diagnostic</html>", {
        status,
        headers: { "Content-Type": "text/html" },
      });
    await assert.rejects(api("/repositories"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.match(error.message, /backend|server|service|unavailable/i);
      assert.match(
        error.message,
        /retry|try again|resume|start|restart|check|wake/i,
      );
      assert.doesNotMatch(error.message, /private-gateway-diagnostic|<html>/);
      return true;
    });
  }
});

test("HTML login redirects and invalid JSON cannot look like a successful API response", async () => {
  for (const [body, type] of [
    ["<html>private-login-page</html>", "text/html"],
    ["broken", "application/json"],
  ]) {
    globalThis.fetch = async () =>
      new Response(body, { headers: { "Content-Type": type } });
    await assert.rejects(api("/repositories"), (error) => {
      assert.match(error.message, availability);
      assert.doesNotMatch(
        error.message,
        /private-login-page|Unexpected token|<html>/,
      );
      return true;
    });
  }
});

test("offline failures have an actionable message and omit raw network diagnostics", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("private-network-diagnostic");
  };
  await assert.rejects(api("/repositories"), (error) => {
    assert.match(error.message, availability);
    assert.doesNotMatch(error.message, /private-network-diagnostic/);
    return true;
  });
});

test("multipart uploads leave the content boundary to the browser", async () => {
  let headers;
  globalThis.fetch = async (_path, options) => {
    headers = new Headers(options.headers);
    return Response.json({ uploaded: true });
  };
  const form = new FormData();
  form.set("branch", "main");
  assert.deepEqual(
    await api("/repositories/upload", { method: "POST", body: form }),
    { uploaded: true },
  );
  assert.equal(headers.has("Content-Type"), false);
});
