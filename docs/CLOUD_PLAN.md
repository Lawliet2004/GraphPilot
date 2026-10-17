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
4. **Verified in the actual cloud:** public HTTPS, secure login, admin API/page,
   worker indexing, graph/source/branch browser journeys, actual HTTP/stdio MCP
   calls and immediate token revocation. Foreign-origin and anonymous access fail.
5. **Published:** source changes and CI checks. The account owner authorized
   Codespaces; a 2-core workspace runs with a 30-minute idle timeout. Browser
   access and cloud SSH work. Paid Codespaces usage remains blocked at $0.

Remaining account-specific steps:

- Create your own cloud account and choose its administrator password through
  the documented trusted-terminal command.
- Select an MCP client and issue a separate expiring token for it.
- No Azure student verification, external SMTP account or application model has
  been supplied. These are optional for the first cloud demo.

Codespaces is for scheduled demos and development. Its free allowance and idle
shutdown are not permanent 24/7 hosting. No paid service will be enabled.

Verification: 120 backend/release tests, three read-only browser checks, one full
Docker browser repository journey, actual HTTP/stdio MCP calls, token revocation,
and Docker stop/resume with retained sessions, graph and source evidence pass.
Ruff, frontend build, Actionlint, Python dependency audit and candidate-only secret
scan pass. See `CLOUD_VERIFICATION.json` for the separate local and actual-cloud
evidence. QA uses disposable labeled accounts; no paid agent/model is running.
