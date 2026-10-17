# Short Vercel demo address

The deployed production website is **https://gp-code.vercel.app**, in project
`gp-demo` on the existing Hobby team. The old generated Vercel alias redirects to
it. Firebase user/admin login, scoped CLI, private-source MCP, rejected foreign
origins and public security headers passed through this domain. The GitHub App's
additional callback is prepared in the browser but still requires the owner's
approval before saving; fresh GitHub connections on this domain must not be
called verified until that callback is saved and exercised.

Deploy the `app` directory as a Vite project on the existing Vercel Hobby account.
The target name is `gp-demo`; the actual `.vercel.app` alias depends on availability.
Vercel serves the built frontend and proxies `/api/*` to the existing Codespaces
gateway. No Firebase password, GitHub secret, encryption key or database credential
belongs in the frontend deployment. API responses must remain uncached.

The checked-in `app/vercel.json` supplies the build, API rewrite, SPA fallback and
security headers. Its backend destination is the current demo's public gateway.
Update that destination and redeploy when the backend moves to Azure.
The API uses a named `(.*)` capture to preserve the trailing slash required by MCP;
the SPA/header matcher also includes the root path. API data remains uncached.

After the Vercel production domain is assigned:

1. Add `https://SHORT-HOST/api/integrations/github/callback` in the GitHub App's
   authorized callback URLs. Keep the old callback during the transition.
2. On the existing backend, pull this source and run:

   ```bash
   python3 scripts/cloud_demo.py start \
     --public-url https://SHORT-HOST \
     --allowed-origin https://YOUR-CODESPACE-18080.app.github.dev
   ```

   This changes the canonical browser origin, retains the old exact API origin,
   and redirects old frontend pages to the canonical website. It preserves
   private credentials and persistent volumes. Later starts retain the custom
   domain and allowed origins. The health check uses local API readiness.
3. Verify through the short domain: Firebase user/admin login, authenticated POST
   with CSRF, rejected foreign origins, CLI pairing/revocation, MCP and selected
   private-repository access. Test a fresh browser GitHub OAuth callback. Do not
   claim the move is finished based only on a successful frontend build.
4. Update private CLI/MCP client configuration and owner access notes after the
   production checks pass. Never share an owner token or password in a public URL.

Vercel's frontend availability does not keep Codespaces awake. The current backend
still has idle shutdown and finite free allowances. Always-awake backend hosting
remains dependent on Azure student verification and a separately verified migration.

Sources: [Vercel external rewrites](https://vercel.com/docs/routing/rewrites),
[Vercel Hobby plan](https://vercel.com/docs/plans/hobby).
