# Always-awake student demo hosting

The requested host is pending Azure for Students verification. No Azure VM,
subscription upgrade or paid service has been created by this setup. The current
Codespaces URL is an on-demand demo and can stop after inactivity.

Azure for Students advertises no credit card and a finite credit allowance.
Eligibility, regional capacity and the actual subscription's spending protection
must be verified before creating resources. Do not enable pay-as-you-go, enter a
card, or assume every VM, disk and public IP is included in the free allowance.

## Deployment steps after verification

1. Confirm an active **Azure for Students** subscription and enabled spending
   limit. Check the remaining balance and end date. Use one resource group for
   this demo. Review the actual combined VM, disk and IP cost before creation.
2. Choose a small Ubuntu Linux VM with enough memory for PostgreSQL, FalkorDB,
   API and worker (target at least 4 GB). Install Docker Engine, Compose v2,
   Python 3 and Git from their official sources. Use an SSH key; restrict SSH to
   the owner's IP and allow public HTTP/HTTPS only. Never expose database ports.
3. Clone this repository and copy only the deployment's private configuration to
   the VM over SSH. Keep file mode 600. Preserve the Firebase project settings
   and GitHub encryption key; do not copy developer `.env` files or unrelated
   local credentials. Transfer the controlled demo's database and artifact
   backups privately if retaining its users and indexed source.
4. Assign a stable DNS name to the public IP. Configure a trusted HTTPS reverse
   proxy (for example Caddy) on ports 80/443, forwarding to `127.0.0.1:18080`.
   Start GraphPilot with the real HTTPS origin:

   ```bash
   python3 scripts/cloud_demo.py start --build --public-url https://YOUR-HOST
   python3 scripts/cloud_demo.py check
   ```

   The existing Compose stack supplies private networks, durable volumes,
   migrations and `unless-stopped` restart policies. Enable Docker at boot. Keep
   the web port bound to loopback; HTTPS is the public entry point.
5. Add the final origin to Firebase's authorized domains if required for enabled
   sign-in methods, and update the GitHub App callback to
   `https://YOUR-HOST/api/integrations/github/callback`. Configure its private
   environment settings as described in [GitHub and CLI](GITHUB_AND_CLI.md).
6. Verify a normal Firebase user and the existing admin, two users' repository
   isolation, a selected private repository, indexing, evidence, history sync,
   browser-approved CLI and authenticated MCP. Reboot the VM and confirm the
   website, database, graph and source persist. Exercise backup/restore on a
   separate disposable target before relying on backups.
7. Run `python3 scripts/demo_check.py --url https://YOUR-HOST` from an external
   machine. Schedule that read-only check against the stable URL, retain short
   logs, and monitor credits/disk space. A free monitor does not prevent provider
   outages or extend expired student credits. Keep Codespaces until this host
   passes its live verification, then stop the unused workspace.

The account holder must complete academic verification and accept applicable
account terms. The current signup form has not completed verification; entering
a school name alone does not activate a subscription. If that form rejects the
school, use Microsoft's visible support/verification flow rather than bypassing
its controls.

Sources: [Azure for Students](https://azure.microsoft.com/en-us/free/students/),
[Azure spending limit](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit),
[Caddy reverse proxy](https://caddyserver.com/docs/quick-starts/reverse-proxy).
