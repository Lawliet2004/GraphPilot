# Professional small-team demo

## Accepted requirements

- Public website with Firebase sign-in and separate normal/admin permissions.
- A few simultaneous users are expected. There is no five-account or five-session cap.
- Connect each user's GitHub account and select public/private repositories.
- CLI commands use that user's own GraphPilot permissions.
- The website must stay running, independently of the developer's computer.
- No credit card or pay-as-you-go subscription is authorized.

## Hosting decision

The owner has a college email and can verify Azure for Students eligibility.
College-account portal sign-in is complete, but Microsoft student verification
rejected the university ID. The official GitHub Education redemption returned to
the same verification form. Student activation and spending protection remain
unverified; the account/subscription support workflow is being reviewed.
The proposed host is a small Linux VM running the existing Docker Compose stack,
with persistent volumes, a public HTTPS gateway and restart policies. Firebase
continues to manage authentication. PostgreSQL, FalkorDB and source artifacts
remain private on the host; they are not put on ephemeral free web-service disks.

Azure student credits are finite, not permanent free hosting. Before provisioning,
verify the active student subscription, spending protection, region/SKU availability
and the VM, disk and public-IP cost shown for that subscription. Keep paid upgrades
disabled. Do not substitute a credit-card trial. The current Codespaces demo stays
available until the new deployment passes authentication, indexing, private-repo
access, CLI and restart/persistence checks.

Render's free web services sleep after 15 idle minutes and lose local files, so
they do not meet the accepted always-awake requirement. Codespaces remains a
development/demo environment and does not meet that requirement either.

## Implementation sequence

1. Prepare a GitHub App connection with PKCE, one-time session-bound state,
   encrypted user tokens and selected-repository access. Request only read access
   to metadata, contents and Actions. Support token refresh and disconnect.
2. Add browser-approved CLI credentials with explicit read/manage scopes,
   expiry and revocation. The CLI must not accept administrator commands or run
   repository code on the host. Provide repository connect/list/index/status,
   symbol search and source-evidence commands.
3. Extend the existing connection screen with the authorized GitHub repository
   picker, loading/empty/error states and clear installation controls. Keep public
   URL and ZIP upload available.
4. Register the actual GitHub App against the current demo callback, then update
   it when the final Azure HTTPS origin is known. The owner reviews repository
   permissions before granting the installation.
5. After Azure verification, provision the agreed host, migrate the controlled
   demo data, configure HTTPS/Firebase callback origins, and test the complete
   normal-user journey with an actual selected private repository.
6. Verify multiple concurrent users and tenant isolation, restart persistence,
   backups and restore. Enable monitoring against the stable public URL.

## Evidence and account-dependent boundaries

The existing cloud demo has Firebase login, role checks, real public-repository
indexing and five read-only MCP tools. A GitHub App connection, private-repository
access and the new always-awake deployment must not be called complete before
their live checks pass. The GitHub/CLI implementation and automated checks are
ready. The actual App is now registered, installed for two selected repositories
and authorized by the owner. A synthetic private repository passed live indexing,
source evidence, history sync and another user's access-denial checks. CLI and MCP
also passed live cloud checks. Always-awake Azure hosting remains pending academic
verification. See [verification evidence](GITHUB_CLI_VERIFICATION.json),
[GitHub and CLI](GITHUB_AND_CLI.md) and
[Azure deployment steps](AZURE_HOSTING.md).

The frontend is now published at [gp-code.vercel.app](https://gp-code.vercel.app)
on Vercel Hobby. The backend remains in Codespaces. See
[Vercel verification](VERCEL_VERIFICATION.json) for live checks and the pending
new-domain GitHub callback, currently blocked by GitHub Confirm access.
Live personal-key synthesis, actual Firebase mail receipt, restart persistence,
off-host backup and isolated restore now have verification evidence in
[cloud operations](CLOUD_OPERATIONS_VERIFICATION.json). This frontend move does not satisfy the
always-awake backend requirement.

Sources: [Azure for Students](https://azure.microsoft.com/en-us/free/students/),
[Render free-service limitations](https://render.com/docs/free),
[GitHub App user authorization](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app).
