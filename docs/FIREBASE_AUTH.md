# Firebase authentication for the free demo

The demo uses Firebase Authentication on the Spark plan for email/password
credentials, verification email and password-reset email. PostgreSQL keeps
GraphPilot profiles, administrator roles, repository ownership and memberships.
Neither Firestore nor a service-account private key is required. Firebase does
not run the Python API, worker or graph database; those remain in Codespaces.

Project: `graphpilot-demo-20261017`.
[Firebase console](https://console.firebase.google.com/project/graphpilot-demo-20261017/authentication/users).
The console showed **Spark, no cost ($0/month)** during setup. No billing account,
SMS provider, Cloud Functions, Storage, paid model or recurring agent was enabled.
Free quotas still apply. Codespaces remains an on-demand demo with an idle timeout.

## Configuration and deployment

Set these values in the deployment's private environment file, never Git:

```dotenv
GP_FIREBASE_PROJECT_ID=your-project-id
GP_FIREBASE_API_KEY=your-firebase-web-api-key
```

Use the project's Web API key, not a service-account credential. Enable
email/password with the checked-in `firebase.json`:

```bash
npx -y firebase-tools@15.34.0 login
npx -y firebase-tools@15.34.0 deploy --only auth --project YOUR_PROJECT_ID
uv run alembic upgrade head
```

For the cloud demo, update its existing owner-only
`.data/cloud-demo/graphpilot-cloud-demo/compose.env`, then rebuild the deployment
with `python3 scripts/cloud_demo.py start --build`. Preserve the database settings.
The controller keeps the Firebase settings on subsequent starts. Production
requires HTTPS and secure cookies. Do not set `GP_FIREBASE_EMULATOR_HOST` there.

The browser continues to use GraphPilot's same-origin forms and CSRF protection.
The API exchanges credentials with Google's official Auth REST endpoint. Provider
ID tokens are kept in an HttpOnly cookie, never localStorage or response JSON.
Sessions last at most one hour; sign in again when they expire. Each authenticated
browser request checks the provider account and revocation boundary. There is no
refresh-token storage or automatic refresh in this first demo integration.

## Normal accounts and administrators

New signup creates a normal GraphPilot user. It never accepts administrator roles
from form fields or provider claims. Normal users can manage their own repositories
and use repositories explicitly shared with them. Administrators can manage users,
memberships and operational settings; repository access remains permission checked.

After the owner signs up, promote that existing account in the trusted API container:

```bash
python -m api.cli promote-admin you@example.com
```

Existing local accounts keep their original login until explicitly migrated. Do
not merge identities merely because their emails match. After verifying the
correct Firebase UID through the console/MCP, the trusted operator may run:

```bash
python -m api.cli link-firebase you@example.com VERIFIED_FIREBASE_UID
```

This preserves the SQL account ID, role and repository ownership, replaces the
local password hash, and revokes its previous browser sessions and MCP tokens.
The linked account must subsequently sign in through Firebase; local-password
fallback is disabled. Create replacement read-only MCP tokens when needed.
MCP bearer tokens have their own expiry/revocation and are not Firebase ID tokens;
disable the GraphPilot user or revoke those tokens to terminate agent access.

Settings shows email-verification status and a resend button. Firebase's hosted
email-action pages handle verification and password reset. Use a real email inbox
to receive them. The shared demo and GitHub noreply login IDs are not inboxes.
Actual Gmail delivery was verified on 2026-10-17 with a unique test alias: the
verification action succeeded and GraphPilot displayed the verified status. The
verification message was in Inbox. The reset message arrived in Spam and its
code validated; the user completes the password change on the hosted action page.
This proves receipt, not reliable Inbox placement for reset mail. No real inbox
address or action code is stored in public evidence.

Email verification is displayed but is not a prerequisite for this hackathon's
repository features. While Firebase is enabled, reset emails apply to Firebase
accounts only. Migrate existing local accounts deliberately before relying on
that flow; an operator can otherwise reset their local credentials in the trusted
terminal. Never claim email delivery was tested from emulator evidence alone.

## Official Firebase MCP

The official Firebase CLI supplies the MCP server. This computer's Codex config
has a server named `firebase`, using the cached pinned version and this checkout:

```bash
codex mcp add firebase -- npm exec --offline --yes \
  --package=firebase-tools@15.34.0 -- firebase mcp --only auth \
  --dir /absolute/path/to/GraphPilot
codex mcp get firebase
```

Its official auth tools and always-available core project tools use the signed-in
Firebase CLI account. The CLI's private credential store stays outside Git.
Restart the client if it needs to reload newly registered servers. On a new
machine install/cache the pinned package and sign in first. This server manages
Firebase; GraphPilot's separate `/api/mcp/` endpoint exposes read-only code tools.

## Verification

Backend tests cover normal/admin separation, CSRF, account collision protection,
disabled/revoked sessions, explicit migration and the absence of native-password
fallback for linked users. An opt-in test exercises Google's actual Auth emulator:

```bash
npx -y firebase-tools@15.34.0 emulators:start --only auth \
  --project demo-graphpilot --config /path/to/local-emulator.json
GP_TEST_FIREBASE_EMULATOR=1 uv run pytest tests/test_firebase_auth_emulator.py -q
```

Configure that emulator on `127.0.0.1:19099`. The test verifies real signup,
verification, password reset, old-password rejection, session invalidation and
logout. It creates disposable emulator identities only. Production config rejects
emulator use and non-loopback emulator addresses.

References: [official Firebase MCP](https://firebase.google.com/docs/ai-assistance/mcp-server),
[Auth REST API](https://firebase.google.com/docs/reference/rest/auth),
[Spark billing](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans),
[Auth limits](https://firebase.google.com/docs/auth/limits),
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
