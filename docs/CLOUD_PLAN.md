# Cloud demo and integrations plan

Goal: run the real GraphPilot stack in the cloud for interviews/hackathons,
without a payment card, while keeping existing authentication and permissions.

1. **Implemented:** a repeatable Codespaces configuration and isolated Docker demo controller.
   Generate private deployment secrets, use the forwarded HTTPS origin, preserve
   database/artifact volumes and keep database ports private.
2. **Implemented:** authenticated read-only MCP tools, expiring per-user credentials,
   explicit revocation and a portable local bridge for compatible MCP clients.
3. **Implemented:** a free QA runner and GitHub workflow for deployment health, access
   restrictions and browser checks, with reports and no model/API subscription.
4. **Locally verified:** migrations, authorization boundaries, real MCP discovery/tool calls,
   container startup and browser journeys. Record evidence, not just configuration.
5. Publish reviewed source changes and verify CI. Leave account-specific actions
   to the user when the account cannot authorize them here.

Current external blockers:

- The GitHub CLI is signed in as Lawliet2004 but lacks the `codespace` scope.
  Creating/listing Codespaces returns HTTP 403. The account owner must authorize
  that scope or create the workspace in GitHub's web interface.
- Chrome's computer-use connection fails to load its request-header policy before
  any tab can be read or opened. No browser changes have been made.
- No Azure student verification, external SMTP account or application model has
  been supplied. These are optional for the first cloud demo.

Codespaces is for scheduled demos and development. Its free allowance and idle
shutdown are not permanent 24/7 hosting. No paid service will be enabled.

Verification: 120 backend/release tests, three read-only browser checks, one full
Docker browser repository journey, actual HTTP/stdio MCP calls, token revocation,
and Docker stop/resume with retained sessions, graph and source evidence pass.
Ruff, frontend build, Actionlint, Python dependency audit and candidate-only secret
scan pass. See `CLOUD_VERIFICATION.json` for the exact local scope. The actual
Codespace and its public HTTPS behavior still require account authorization.
