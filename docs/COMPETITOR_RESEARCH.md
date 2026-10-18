# Competitor research — developer workspace tooling

Research date: **2026-10-18**. Every workflow claim below comes from the vendor's
own documentation or GitHub's official docs/CLI manual — no third-party
promotional posts, no pricing asserted from memory, no UI-screenshot claims.
Sources are listed at the end with the same access date.

Two sections are kept deliberately separate:

- **Verified competitor facts** — what the official documentation actually says.
- **GraphPilot product decisions** — our prioritized implementation brief,
  derived from those facts but scoped to our architecture (typed HTTP API,
  durable jobs, membership-checked graph/evidence routes, no command-execution
  surface).

---

## Verified competitor facts

| Product | Verified workflow (official docs) | Friction GraphPilot can reduce | Official source |
| --- | --- | --- | --- |
| **Cursor CLI** (`agent`) | Terminal agent with three modes matching the editor: Agent (default), Plan, Ask (read-only exploration). Interactive TUI by default; `-p/--print` headless mode prints the answer for scripts/CI, with `--output-format text\|json\|stream-json`. `--force`/`--yolo` permits unattended file changes; `CURSOR_API_KEY` authenticates scripts; `--sandbox` toggles command sandboxing; `-w/--worktree` runs in a new Git worktree. | A developer should be able to ask a repository question and get a stdout answer in one command. GraphPilot's equivalent is read-only by design — an `ask` CLI command hits the existing scoped `/context` route and returns evidence + citations rather than edits. | https://cursor.com/docs/cli/overview · https://cursor.com/docs/cli/headless · https://cursor.com/docs/cli/using · https://cursor.com/docs/cli/reference/parameters |
| **Continue CLI** (`cn`) | `cn` opens an interactive TUI; `cn -p "prompt"` is headless single-shot (e.g. `git diff --staged \| cn -p "…commit message…"`). `@` adds file context, `/` runs slash commands, `--resume` continues a session. Per-tool permissions (`allow`/`ask`/`exclude` via `--allow`, `--ask`, `--exclude`, persisted in `permissions.yaml`); `ask`-level tools are auto-excluded in headless mode. `--readonly` is a plan/read-only mode; `cn login` uses a browser flow, `CONTINUE_API_KEY` for CI; shares `config.yaml` and MCP tool config with the IDE extensions. | Graduated, explicit tool permissions and resumable sessions are table stakes. GraphPilot already has browser-approved device-code login (mode-600 credential, `--write` scope) — the missing piece is question/job verbs so `graphpilot ask` works like `cn -p` for evidence answers. | https://docs.continue.dev/cli/quickstart · https://docs.continue.dev/cli/headless-mode · https://docs.continue.dev/cli/tool-permissions |
| **Amp** (Sourcegraph) | `amp` starts a local thread (TUI); `amp -x "prompt"` execute mode prints the final message and exits (auto-enabled when stdout is redirected); `amp -ox` runs the prompt in a cloud "orb" and prints a shareable thread URL; `--executor runner:` targets self-hosted runners; `amp threads continue/list/search/rename/archive/delete` manage threads across CLI, web and mobile. `AMP_API_KEY` accepts a `sgamp_` access token. Context is explicit: `@`-mention files, `AGENTS.md` files, plus tool-gathered context; Ctrl+O opens a command palette in the CLI; `ide connect` links an editor. | Threads survive surface switches — a question asked in the CLI is viewable in the web app. GraphPilot conversations already persist server-side, so a CLI `ask` that writes the same conversation history gives users CLI→web continuity for free. A Ctrl+K palette is a verified pattern for surfacing actions without leaving the workspace. | https://ampcode.com/docs/cli · https://ampcode.com/docs/cli/execute-mode · https://ampcode.com/docs/cli/spawning-orbs · https://ampcode.com/docs/threads · https://ampcode.com/guides/context-management · https://ampcode.com/docs/cli/settings |
| **Coder workspaces** | A workspace is a Terraform-provisioned dev environment with three states: Running / Stopped / Deleted. Start/stop/restart via dashboard, `coder` CLI (`coder start`, `coder stop`, `coder restart`) or REST API. Cost control is first-class: `coder schedule {show\|start\|stop\|extend}` sets per-workspace autostart (time-of-day) and autostop (after N hours); inactivity detection with a template-configured "activity bump" (default 1 h); licensed templates add dormancy and auto-deletion of idle workspaces. | Remote environment lifecycle is exposed as one-command operations plus schedules. GraphPilot's demo backend lives in a Codespace — the same "one command to resume, one to stop" model maps directly onto `gh codespace`/`gh api` fixed commands. | https://coder.com/docs/user-guides/workspace-lifecycle · https://coder.com/docs/user-guides/workspace-scheduling · https://coder.com/docs/reference/cli/schedule |
| **GitHub Codespaces / `gh`** | `gh codespace` (alias `gh cs`) subcommands per the CLI manual: `code`, `cp`, `create`, `delete`, `edit`, `jupyter`, `list`, `logs`, `ports`, `rebuild`, `ssh`, `stop`, `view` — there is **no `start` verb**. A stopped codespace is restarted by connecting (`gh codespace code [-c NAME]`, `code --web` for the browser editor, `gh codespace ssh`) or via REST `POST /user/codespaces/{codespace_name}/start` (token needs the `codespace` scope; GitHub Apps need `codespaces_lifecycle_admin`). Closing the browser tab does **not** stop a codespace; default idle timeout is 30 min (configurable 5–240), a session has a 12 h maximum lifetime, and stopped codespaces are auto-deleted after 30 days (default, configurable). Stopped codespaces still consume storage allowance. | Codespace lifecycle is scattered across an interactive picker and a dashboard. A fixed-command `graphpilot runner status\|start\|stop` — run on the user's own machine where `gh` is already authenticated — removes the dashboard trip and makes "is the demo backend asleep?" answerable in one command. | https://cli.github.com/manual/gh_codespace · https://docs.github.com/en/codespaces/developing-in-a-codespace/using-github-codespaces-with-github-cli · https://docs.github.com/en/codespaces/developing-in-a-codespace/stopping-and-starting-a-codespace · https://docs.github.com/en/codespaces/developing-in-a-codespace/opening-an-existing-codespace · https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle · https://docs.github.com/en/rest/codespaces/codespaces |

### Verified cross-product patterns

- **Headless single-shot is the CLI baseline.** `agent -p`, `cn -p`, `amp -x`
  all mean "one prompt, print answer, exit, scriptable stdout". GraphPilot's
  `ask` should follow the same contract.
- **Permissions are explicit and read-biased by default.** Cursor's Ask mode,
  `cn --readonly` and `ask`-level tool exclusions in headless mode, and Amp's
  auth-scoped tokens all keep unattended runs safe. GraphPilot's read-only
  CLI credential (no `--write`) is already aligned; keep it the default.
- **Environment lifecycle = status + start + stop, nothing more.** Coder and
  Codespaces both reduce it to three operations plus scheduling. Our
  Codespace control needs the same three verbs — not a terminal.
- **Our browser will show actions and real state.** A simulated terminal would
  add no execution capability. Commands belong in the real CLI; the web provides
  discovery, copy-ready commands and repository investigation.

---

## GraphPilot product decisions — prioritized implementation brief

Everything below is a product decision for GraphPilot, not a competitor fact.
Shared constraints that must hold: the three repository tabs (**Ask / Code /
Activity**) stay as they are; evidence display, server-side permission checks
and per-user BYOK are preserved unchanged; no arbitrary web shell API, no
fake terminal, no metrics that don't come from real API data.

### P1 — Actionable repository overview (clean developer workspace)

The `/workspace` dashboard already renders real data: repo cards with status,
files/functions/relationships counts, branch and commit; recent queries;
CI failures; activity. Make it *actionable* with frontend-only changes driven
by the existing `/repositories` payload:

- Per-card next step derived from real state: `failed` → link into the repo's
  job/sync controls, awaiting index → the existing Sync flow, `ready` → deep
  link to the Ask tab. No invented health scores or metrics.
- Deep links use the scoped URL pattern already used by "Recent queries"
  (`scoped()` helper + branch/snapshot params).
- Keep the working summary counters (repos, indexed entities, awaiting work);
  do not add counts we can't source from an endpoint.

*Why:* every verified competitor reduces the distance between "open the tool"
and "act on the repo". Ours should be one click from card → Ask tab.

### P2 — Command palette (Ctrl/Cmd+K)

A keyboard-opened palette inside `Shell`, consistent with the verified
Ctrl+O/VS Code-pattern palettes:

- Entries: repositories by name (from the existing `/repositories` query),
  per-repo Ask/Code/Activity deep links, Connect, Activity, Settings.
- Actions route only to existing typed endpoints — e.g. "Sync source" issues
  the same `POST /repositories/:id/jobs?kind=index` the repository page uses.
  The palette is a navigator, never a command line: no free-text execution,
  no shell-like verbs.
- Keyboard-first: `↑/↓` select, `Enter` go, `Esc` close, labeled input;
  respect existing focus/reduced-motion rules in DESIGN.md.

### P3 — Real Developer Tools page

A page (`/tools`, linked from the workspace navigation) that surfaces **only** real
server state:

- Active CLI credentials and revocation (the data already behind
  Settings → CLI & agent access).
- Links to existing CLI credential management. Do not invent MCP status without
  an endpoint that actually reports it.
- API/database readiness from the existing health endpoint.
- Copy-ready `graphpilot` commands (login, ask, jobs, codespace verbs).

If a backing call fails, show the shared `ErrorNotice`. No embedded terminal,
no simulated output, no "live" indicators not backed by a query.

### P4 — `graphpilot ask` and `graphpilot jobs` CLI commands

Extend `api/client.py` (and the `scripts/graphpilot` shim) using existing
routes only:

```bash
./scripts/graphpilot ask REPOSITORY_ID "where is authentication handled?" [--branch B]
./scripts/graphpilot jobs list REPOSITORY_ID       # GET /repositories/:id/jobs
./scripts/graphpilot jobs cancel JOB_ID             # explicit cancellation
```

- `ask` → `POST /api/repositories/:id/context` with `{question}`, honoring
  the existing branch/snapshot scoping. Prints the answer (AI synthesis when
  the user's BYOK key is configured server-side; graph retrieval + notice
  otherwise — identical to the web contract), citations and a retrieval
  diagnostics in a JSON response for scripting. The conversation lands in the
  same history the web Ask tab shows.
- Job listing works with a read-only credential. The current authorization
  policy requires `login --write` for question submission and cancellation,
  because these are POST operations. Preserve that policy and explain it in
  the command builder. These verbs call typed endpoints, never a shell API.

### P5 — Local daily Git workflow

Keep local Git operations independent of website login and network availability:

```bash
./scripts/graphpilot git daily --path .
./scripts/graphpilot git switch feature/search --create --path .
./scripts/graphpilot git stage app/src/page.tsx --path .
./scripts/graphpilot git commit --message "Improve search" --path .
```

Daily status combines the branch, working tree, upstream distance and recent
commits. Staging takes explicit paths; commits use already staged changes.
Pull uses fast-forward only and push uses the configured upstream. Do not
force-push, auto-stage, auto-commit, or confuse this local checkout with a
server-local ingestion path.

### P6 — Fixed-command lifecycle control of the existing Codespace

The demo backend runs in the user's existing GitHub Codespace. Implement
control **in the local CLI**, not the web API:

```bash
./scripts/graphpilot runner status   # gh codespace list --json name,state,repository
./scripts/graphpilot runner start    # gh api -X POST user/codespaces/NAME/start
./scripts/graphpilot runner stop     # gh codespace stop -c NAME
```

- `NAME` comes from a validated named runner profile stored privately beside
  the CLI config. Profile configuration names an existing Codespace explicitly.
  Commands are fixed `argv` arrays run via `subprocess` (no shell); `gh`
  must be installed and `gh auth`-ed on the user's machine, else a clear
  error. This matches the verified lifecycle surface exactly: status/start/stop.
- Deliberately *not* a server route: the hosted API runs inside the Codespace
  itself, so a server-side stop would kill the API mid-request, and a web
  shell-execution surface violates the project's "no command execution API"
  rule. If in-UI buttons are ever wanted, the only acceptable shape is an
  admin-only typed endpoint invoking a hardcoded argv template — recommend
  the client-side CLI design instead.

---

## Boundaries (explicit non-goals)

- No arbitrary web shell or terminal emulation in the browser.
- No changes to evidence panels, citation handling, permission/membership
  checks, or BYOK model-key storage — this brief adds surface area, it does
  not remove it.
- No new LLM dependency: `ask` works in graph-retrieval mode without a key.
- Keep repository navigation at exactly three tabs: Ask / Code / Activity.

## Sources

All accessed 2026-10-18:

- https://cursor.com/docs/cli/overview
- https://cursor.com/docs/cli/headless
- https://cursor.com/docs/cli/using
- https://cursor.com/docs/cli/reference/parameters
- https://docs.continue.dev/cli/quickstart
- https://docs.continue.dev/cli/headless-mode
- https://docs.continue.dev/cli/tool-permissions
- https://ampcode.com/docs/cli
- https://ampcode.com/docs/cli/execute-mode
- https://ampcode.com/docs/cli/spawning-orbs
- https://ampcode.com/docs/threads
- https://ampcode.com/guides/context-management
- https://ampcode.com/docs/cli/settings
- https://coder.com/docs/user-guides/workspace-lifecycle
- https://coder.com/docs/user-guides/workspace-scheduling
- https://coder.com/docs/reference/cli/schedule
- https://cli.github.com/manual/gh_codespace
- https://docs.github.com/en/codespaces/developing-in-a-codespace/using-github-codespaces-with-github-cli
- https://docs.github.com/en/codespaces/developing-in-a-codespace/stopping-and-starting-a-codespace
- https://docs.github.com/en/codespaces/developing-in-a-codespace/opening-an-existing-codespace
- https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle
- https://docs.github.com/en/rest/codespaces/codespaces
- https://docs.github.com/en/billing/concepts/product-billing/github-codespaces

## Acceptance criteria

- **Overview:** repository cards show a next-step action derived solely from
  fields already in `GET /repositories`; links carry branch/snapshot scope;
  no new metrics appear.
- **Palette:** opens via Ctrl/Cmd+K and a visible control; lists live
  repositories; every action maps to an existing typed endpoint; fully
  keyboard-operable; adds zero new API routes.
- **Developer Tools:** renders CLI credential and API readiness data from real
  endpoints, generates valid commands and reports copy failures; no terminal.
- **CLI:** job listing works read-only; `ask` and cancellation honor the existing
  repository-management scope; `ask` output includes citations/diagnostics and lands
  in the same conversation history as the web Ask tab; output is JSON;
  error paths keep the no-secret-echo contract.
- **Codespace:** `runner status/start/stop` invoke fixed `gh`/`gh api`
  argv only; unit checks prove injected names can't alter the command; clear
  error when `gh` is missing or unauthenticated; no server-side shell route.
- **Invariants:** Ask/Code/Activity tabs, evidence, permissions and BYOK
  unchanged; `ruff`, `pytest`, `npm run build` green; this file is the only
  research deliverable.
