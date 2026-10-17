# Free cloud demo, MCP and QA

## Start the cloud demo

The account's first **GraphPilot demo** Codespace has been created on the 2-core
machine, with a 30-minute idle timeout and port 18080 public. Open the existing
workspace from [your Codespaces dashboard](https://github.com/codespaces) to resume
it; avoid creating a duplicate for every demo. The exact public URL is recorded
in `CLOUD_VERIFICATION.json`. GitHub displays a one-time development-port notice
before the website. Choose **Continue** for your own demo.

For a separate new demo, open [GraphPilot in Codespaces](https://codespaces.new/Lawliet2004/GraphPilot),
choose the **2-core** machine and create the workspace on `main`. The dev container
installs Docker support and starts the complete stack automatically. The first
build may take several minutes. If needed, run:

```bash
python3 scripts/cloud_demo.py start
python3 scripts/cloud_demo.py check
```

Open **Ports → 18080 → Open in Browser**. When ready to share, choose
**Port Visibility → Public** and copy its HTTPS URL. Only this web port should be
forwarded. Keep PostgreSQL, FalkorDB and the API's direct port private. The app
keeps its own signup/login, repository permissions and admin authorization.

Create your account through the website. To make your own administrator:

```bash
python3 scripts/cloud_demo.py admin --email you@example.com
```

With local authentication this prompts for a password and replaces that account's
password. With [Firebase Authentication](FIREBASE_AUTH.md) configured, sign up first;
the command only promotes the existing account and keeps its Firebase credentials.
No default account is shipped. Admin status does
not bypass repository membership. Connect a small public Python repository or
upload `fixtures/reference` as a ZIP for an interview demonstration.

```bash
python3 scripts/cloud_demo.py status
python3 scripts/cloud_demo.py stop
python3 scripts/cloud_demo.py start
```

Stop preserves database and uploaded-source volumes. Start keeps the generated
database password and refreshes the HTTPS origin if the Codespace hostname changes.
Development `.env`, the native stack and the existing Quick Tunnel deployment are
separate. Private generated configuration lives under `.data/cloud-demo/`.
The controller needs Python 3 and Docker only. `--build` rebuilds changed source.
For local validation, choose another `--project graphpilot-cloud-check --port 18081`.
Later starts preserve an existing HTTPS URL even when SSH omits Codespaces
environment variables. The gateway restores Codespaces' rewritten browser origin
only for the configured forwarded host and same-origin Fetch Metadata. Foreign
and missing browser origins remain restricted. The web gateway has its own health
check and is recreated on start so updated configuration is applied.

Codespaces is an on-demand development/demo environment, not permanent hosting.
GitHub Free currently includes 120 core-hours (60 hours on 2 cores) and 15 GB-month
storage. Both allowances matter; stopped workspaces still use storage. Without a
payment method, usage is blocked when the allowance is exhausted. Set an appropriate
idle timeout before an interview; it can be up to four hours. Your computer may
be off while the Codespace runs, but its URL stops serving when it stops. After
resuming, check the port's visibility again. Do not use keepalive tricks to defeat
provider limits.

The current account's GitHub Pro benefit provides 180 core-hours (90 hours on
2 cores) and 20 GB-month storage. Its Codespaces paid budget was verified at **$0,
usage blocked** before creation, with no usage recorded this month. Keep that
budget in place; free compute and storage allowances are finite.

Sources: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces),
[public ports](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace),
[idle timeout](https://docs.github.com/en/codespaces/setting-your-user-preferences/setting-your-timeout-period-for-github-codespaces).

## Connect an MCP client

The cloud controller enables **`https://YOUR-DEMO-HOST/api/mcp/`**. Ordinary
deployments keep it off unless `GP_MCP_ENABLED=true`. It uses **Streamable HTTP**
with operator-issued bearer credentials. This is not OAuth: clients must support
custom Authorization headers or the included stdio bridge. Automatic OAuth-only
connectors are not supported. The trailing slash is intentional.

Five tools are available: `list_repositories`, `search_symbols`, `read_evidence`,
`inspect_impact`, and `indexing_status`. They cannot modify repositories, users,
jobs or settings, execute code, or submit arbitrary Cypher. Every HTTP request
requires a token. Each tool rechecks the user's repository membership.

Issue a token for an existing account:

```bash
python3 scripts/cloud_demo.py mcp-token --email you@example.com --days 7
```

The command prints a **file path** and non-secret token ID, never the bearer value.
Tokens last 1–30 days, are hashed in PostgreSQL and stop working if revoked,
expired or the user is disabled. Copy the token securely into a compatible client's
Authorization header, or use its owner-only local file with the stdio bridge.
Do not put it in a URL, source control, screenshots or a chat message.

```bash
python3 scripts/cloud_demo.py mcp-revoke --token-id NON_SECRET_TOKEN_ID
```

For a local MCP-capable client, install the source package at
`integrations/graphpilot` using that client's supported local-plugin flow, or use
the command directly:

```bash
export GP_MCP_URL=https://YOUR-DEMO-HOST/api/mcp/
export GP_MCP_TOKEN_FILE=/absolute/path/to/your/private.token
uv run python -m api.mcp_bridge
```

The token file must be a regular file with mode `600`. If the client runs on your
laptop, securely download that file from your Codespace first. Set these two
environment variables in the MCP client's process configuration. The plugin
manifest launches `uv run --project <repository> python -m api.mcp_bridge`; it
needs this checkout and uv, not local database credentials. Logs go to stderr.
Host-specific installation is separate from server verification.

Verify both actual HTTP and stdio transports:

```bash
uv run python -m scripts.verify_mcp --output .data/mcp-check.json
# Optional: --repository-id UUID --query KNOWN_SYMBOL also checks source evidence.
```

For a conventional server deployment, migrate normally and issue credentials via
`python -m api.cli create-mcp-token EMAIL --output PRIVATE_PATH --days 7`.
The corresponding `list-mcp-tokens EMAIL` and `revoke-mcp-token TOKEN_ID` commands
operate from a trusted server terminal. They are never web command-execution APIs.

## Free checks and optional QA agent

```bash
python3 scripts/demo_check.py --url https://YOUR-DEMO-HOST --output .data/demo-check.json
GRAPHPILOT_DEMO_URL=https://YOUR-DEMO-HOST npm run demo:check
```

The HTTP checker tests frontend assets, database readiness, security headers,
anonymous access denial and the MCP authentication gate. The browser checks test
landing-page rendering, mobile login layout, JavaScript errors and admin login
protection. Neither creates accounts, changes data or sends email. Browser checks
need `npm ci` and `npx playwright install chromium`; installed Chrome can be used
with `PLAYWRIGHT_CHANNEL=chrome`.

In GitHub **Actions → Public demo checks → Run workflow**, supply the HTTPS origin
for an on-demand check. Optional: set repository Actions variable
`GRAPHPILOT_DEMO_URL` to enable checks every six hours. Leave it unset for an
on-demand Codespace: scheduled requests should not be used to keep it awake.
Reports are retained for three days. These checks invoke no AI model.

The optional `.github/agents/graphpilot-qa.agent.md` profile gives a compatible
Copilot host a repeatable QA procedure. It does not provision an agent service,
start a model or make an AI subscription free. The existing CI continues to run
the full database tests, authenticated browser journeys, container recovery,
dependency and image audits on pushes.

## Steps the account owner still needs to do

1. Open the demo and create your own account/password. Temporary QA credentials
   are removed after verification; no shared administrator password is shipped.
2. In the cloud terminal, run the administrator command above using your email.
   Enter the password yourself. Your cloud accounts are separate from local ones.
3. Choose your MCP client and issue its own expiring token privately if needed.
4. If password-reset email is required, create/verify an SMTP sender and configure
   the private deployment file. External inbox delivery still requires testing.

Azure for Students is an alternative for longer-running hosting if eligible;
student verification and finite cloud credits are separate from this setup.
