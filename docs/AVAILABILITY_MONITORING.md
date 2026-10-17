# Demo availability monitoring

The `Demo availability` GitHub Actions workflow probes the canonical static
frontend at `https://gp-code.vercel.app` twice an hour. It verifies HTTP success,
the application root, CSP, HSTS and content-type protections. A failed probe fails
the workflow. Use GitHub's Actions notification settings to receive failure
notifications; this implementation does not assert that email notifications are
enabled for the account.

While the backend remains in Codespaces, scheduled probes never call `/api` or
the forwarded Codespace hostname. They do not keep the backend awake and do not
prove API, indexing, authentication, worker or MCP availability. The static
frontend remains available when that backend sleeps. This limited scope is
reported explicitly by the check.

Run the current probe manually:

```bash
python3 -m scripts.uptime_check --url https://gp-code.vercel.app --backend-kind codespaces
```

After moving to a verified always-awake backend, change the workflow argument to
`--backend-kind always-awake`. That additionally requires a successful
`/api/health/ready` response from PostgreSQL and FalkorDB. Do this only after
updating the Vercel API destination and checking restart persistence on the final
host. The readiness endpoint does not prove the worker is processing jobs;
inspect the admin worker observations and a real indexing job after deployment.

Scheduled Actions runs can be delayed or dropped under load. Public repository
schedules are disabled after 60 days without repository activity. This is a free
availability signal, not a guaranteed paging service or SLA. Review the Actions
history and schedule state before a demo.

On the final host, also watch disk capacity, Docker service health and restart
policies, backup age, and Azure credit balance/expiry. Monitoring cannot extend a
free allowance or prevent a provider from suspending an account. Keep the Azure
spending limit enabled and never add a paid fallback automatically.

Source: [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
