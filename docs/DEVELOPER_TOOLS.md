# Developer tools in the `graphpilot` CLI

`scripts/graphpilot` ships three command families:

- **Hosted** (`login`, `repos`, `search`, `evidence`, `ask`, `jobs`, `github`) —
  talk to your hosted GraphPilot workspace with the existing device-login token.
- **`git`** — a local daily Git routine. No GraphPilot login, no network beyond
  what `git pull`/`git push` already do.
- **`runner`** — lifecycle for your own GitHub Codespace cloud runner, driven by
  the installed GitHub CLI (`gh`). No GraphPilot login.

Everything exits `0` on success, `1` on a tool/safety failure (concise message
on stderr), `2` on usage errors. `--help` never touches the network.

The launcher also works from any other checkout. Use its absolute path or add
an alias in your shell configuration, for example:

```sh
alias graphpilot='/absolute/path/to/GraphPilot/scripts/graphpilot'
graphpilot git daily --path .
```

It keeps your current working directory, so `--path .` refers to the repository
you are working in.

## Auth boundary

| Commands | Credential used |
| --- | --- |
| `ask`, `jobs`, `repos`, `search`, `evidence`, `github`, `whoami` | GraphPilot session from `graphpilot login` (`~/.config/graphpilot/session.json`, mode 600). `ask` and `jobs cancel` are write-scoped — use `graphpilot login --server ... --write`. |
| `git *` | none — plain local `git` (`GIT_TERMINAL_PROMPT=0`) |
| `runner *` | local `gh` CLI credentials (`gh auth login`); no GitHub token is ever stored by GraphPilot |

Runner profiles live in `runners.json` **beside** `--config`
(e.g. `~/.config/graphpilot/runners.json`), mode 600, and contain only the
profile name → Codespace name → workspace path. No secrets.

## Daily workflow

```sh
scripts/graphpilot git daily --path ~/src/myrepo      # branch, status, ahead/behind, last 5 commits
scripts/graphpilot git status --path ~/src/myrepo     # short status
scripts/graphpilot git diff --path ~/src/myrepo       # uncommitted diff vs HEAD
scripts/graphpilot git log --path ~/src/myrepo --count 15

scripts/graphpilot git switch --create fix-typo --path ~/src/myrepo
scripts/graphpilot git stage README.md docs/ --path ~/src/myrepo
scripts/graphpilot git commit --message "Fix typo" --path ~/src/myrepo   # staged only

scripts/graphpilot git pull --path ~/src/myrepo       # always --ff-only
scripts/graphpilot git push --path ~/src/myrepo       # normal upstream push, never forced
```

The CLI never auto-stages, auto-commits or auto-pushes. `git stage` resolves
each FILE relative to the given `--path` (a subdirectory works), keeps the
literal path you typed (no glob/pathspec magic — `star*.txt` stages a file
literally named `star*.txt`), and refuses `..` escapes, absolute paths outside
the repo, `.git` internals and symlinks pointing outside the repo. A symlink to
a file inside the repo is staged as the symlink itself. Branch names are
validated before reaching `git switch`.

## Asking the hosted workspace

```sh
scripts/graphpilot login --server https://your-graphpilot.example --write
scripts/graphpilot ask <repository-id> "Where are CLI tokens verified?"
scripts/graphpilot ask <repository-id> "What broke?" --branch feature/x --revision <snapshot-uuid>
scripts/graphpilot jobs list <repository-id>
scripts/graphpilot jobs cancel <job-id>
```

`ask` calls `POST /api/repositories/{id}/context` and prints the full JSON
answer (answer, citations, diagnostics) for scripting. Repository, job and
revision identifiers must be canonical UUIDs — malformed values are rejected
before any HTTP request.

## Cloud runner (your GitHub Codespace)

One-time setup — point a local profile at an **existing** Codespace (find the
name with `gh codespace list`):

```sh
scripts/graphpilot runner configure demo --codespace my-cs-name-abc123
scripts/graphpilot runner list
```

Daily operations:

```sh
scripts/graphpilot runner status            # gh-side state of all profiles
scripts/graphpilot runner start demo        # POST /user/codespaces/{cs}/start via gh api
scripts/graphpilot runner check demo        # SSH: cloud_demo.py status && check
scripts/graphpilot runner logs demo --service api --lines 100
scripts/graphpilot runner ssh demo          # interactive session
scripts/graphpilot runner stop demo         # gh codespace stop -c ...
```

With a single profile, `NAME` may be omitted everywhere. With several profiles
you must name the target — lifecycle actions never accept a raw Codespace name,
only stored profiles, so they cannot hit the wrong runner.

`check` runs exactly the demo's existing `scripts/cloud_demo.py status` and
`check` inside the Codespace; `logs` runs one bounded `docker compose logs
--tail N` (max 5000) against the private `graphpilot-cloud-demo` project
(`api`, `worker`, `web`, `postgres`, `falkordb`). Neither prints env-file
contents. Because `gh codespace ssh` silently starts a stopped Codespace,
`check`/`logs` first verify the stored Codespace reports `Available` via
`gh codespace list` and otherwise refuse with a `runner start` instruction —
read commands never wake a runner. `runner ssh` is the explicit connect path
and may start one.

### Idle limit and recovery

Codespaces stop automatically after the GitHub idle timeout (default 30 min,
configurable per Codespace up to 240). This CLI never keeps a runner alive.
If `runner check`/`logs` fail because the Codespace is shut down, run
`runner start` then `runner status` until the state settles. A **stopped**
Codespace keeps its disk — the demo's `.data/cloud-demo` state and volumes
survive. A **deleted** Codespace loses everything; recreate it on github.com
and run `scripts/cloud_demo.py start` inside it — the CLI deliberately never
creates, deletes, renames or reconfigures Codespaces, and never changes port
visibility.

After a restart, Codespaces can reset a forwarded port to private. If the
existing public demo still redirects to GitHub sign-in while `runner check`
passes, inspect `gh codespace ports -c CODESPACE_NAME`. Restore its previously
public web port explicitly with
`gh codespace ports visibility 18080:public -c CODESPACE_NAME`. Runner lifecycle
commands leave port visibility to you.

### gh prerequisites

Install `gh` and run `gh auth login` (the default scopes cover Codespaces).
Missing `gh` or expired auth produces an actionable error pointing at
`gh auth login`.

## Honest limitations

- `git push` requires an existing upstream; set it once with
  `git push --set-upstream origin <branch>` using regular `git`.
- `git pull` is always `--ff-only`; diverged branches need regular `git` merge/rebase.
- `runner start` is asynchronous — GitHub reports the state transition on
  `runner status` shortly after.
- `runner logs` is a one-shot tail, not a stream; `runner check` only reports
  the demo's fixed health/status checks.
- `runner configure` validates the Codespace name's format but does not confirm
  it exists — use `runner status` to verify.
- SSH-based commands (`check`, `logs`) need the Codespace's sshd (present in
  this repo's devcontainer via the `sshd` feature) and a running Codespace.
