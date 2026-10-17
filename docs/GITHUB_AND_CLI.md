# GitHub accounts and the remote CLI

Firebase continues to handle website identity and passwords. GraphPilot stores
application roles, repository membership and hashed CLI credentials in PostgreSQL.
There is no five-user limit. GitHub authorization is a separate connection: it
lets an already signed-in user select source repositories; it does not replace
Firebase or make that user an administrator.

## Configure the GitHub App

Register a GitHub App owned by the operator. Make it available for installation
by other accounts if friends will connect their own repositories. Request only
read access to Contents, Metadata, Actions, Issues and Pull requests. No webhook
is required. Use this callback URL, replacing the origin with the actual website:

```text
https://YOUR-HOST/api/integrations/github/callback
```

Set these values in the deployment's private environment file, never Git:

```dotenv
GP_GITHUB_CLIENT_ID=
GP_GITHUB_CLIENT_SECRET=
GP_GITHUB_APP_SLUG=
GP_CREDENTIAL_KEY=
```

Generate the encryption key with `Fernet.generate_key()` from Python's
`cryptography` package and save it privately. Keep the same key across restarts,
API/worker processes and backups. Losing or replacing it makes stored GitHub
credentials unreadable. An App private key is not needed for this user-token flow.
Apply migration `0010_github_and_cli` and restart both API and worker after setup.
With `scripts/cloud_demo.py`, the private file is
`.data/cloud-demo/graphpilot-cloud-demo/compose.env`; later starts preserve these
additional settings. Change the GitHub callback when moving to the Azure host.

On the website, open Connect → Continue with GitHub. Authorize the account, then
use Choose repositories in GitHub to install the App for **Only select
repositories**. Return, refresh the installation list and choose a repository and
branch. Users need their own GitHub access as well as App installation access.
Organization policies may require an organization owner's approval.

The connection uses PKCE and a one-use, browser-session-bound state. GitHub user
access/refresh tokens are encrypted at rest and refreshed when necessary. Git
receives authorization only through process environment configuration, not URLs,
arguments or persisted Git config. Connected private repositories never inherit
the operator's global token. Disconnect removes the local credential; existing
indexed snapshots remain until their repository is removed. Revoke the App in
GitHub too when its provider-side grant should end.

## Use the CLI

From this checkout, with `uv` installed:

```bash
./scripts/graphpilot login --server https://YOUR-HOST --write
./scripts/graphpilot whoami
./scripts/graphpilot github installations
./scripts/graphpilot github repos INSTALLATION_ID
./scripts/graphpilot repos connect --github-id REPOSITORY_ID --installation INSTALLATION_ID
./scripts/graphpilot repos list
./scripts/graphpilot repos status GRAPHPILOT_REPOSITORY_UUID
./scripts/graphpilot repos check GRAPHPILOT_REPOSITORY_UUID
./scripts/graphpilot repos index GRAPHPILOT_REPOSITORY_UUID
./scripts/graphpilot repos sync GRAPHPILOT_REPOSITORY_UUID
./scripts/graphpilot search GRAPHPILOT_REPOSITORY_UUID symbol_name
./scripts/graphpilot evidence GRAPHPILOT_REPOSITORY_UUID NODE_ID
./scripts/graphpilot logout
```

Public URL and ZIP connection are also supported:

```bash
./scripts/graphpilot repos connect https://github.com/OWNER/REPO --branch main
./scripts/graphpilot repos upload /path/to/source.zip
```

Login opens a website approval page with a matching code. Approve only a command
you started yourself. Omit `--write` for read-only access; add `--no-browser` to
open the printed approval URL manually. Credentials expire after seven days and
can be revoked in Settings → CLI & agent access. Logout revokes the current
credential. Local credentials use mode 600 under
`~/.config/graphpilot/session.json` (or `XDG_CONFIG_HOME`). No database access or
Firebase password is needed by the CLI.

Repository-management scope also permits removal of owned GraphPilot repositories
through the API (it never deletes the GitHub repository). CLI credentials obey
repository membership and cannot use administrator APIs,
change browser sessions, or run shell commands. They are independently revocable
GraphPilot credentials: Firebase browser-token expiry/password changes do not
automatically revoke them. Disable the GraphPilot user or revoke credentials in
Settings to end CLI access immediately. Existing read-only MCP tools remain
read-only even when using a credential with repository-management scope.

`check` reports graph/index status and recorded job/CI information. It does not
execute tests or other code from an uploaded or connected repository. Use GitHub
Actions in the repository itself for code execution.

## Verification boundary

Real SQL/backend tests cover permissions, PKCE, encrypted storage, refresh,
disconnect, scoped CLI pairing/revocation and command routing. Provider responses
in automated GitHub tests are mocked. Browser tests exercise real signup, CLI
approval and revocation; the GitHub picker browser test uses an explicitly mocked
provider fixture. A live selected-private-repository test is required after the
operator registers, installs and authorizes the actual App. Do not describe mock
screenshots as a working provider connection.
