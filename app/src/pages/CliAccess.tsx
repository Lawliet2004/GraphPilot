import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post, date } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Brand, ErrorNotice, Loading } from "../components/ui";

export function CliAccess() {
  const auth = useAuth();
  const [params] = useSearchParams();
  const code = (params.get("code") || "").replaceAll("-", "").toUpperCase();
  const valid = /^[A-F0-9]{8}$/.test(code);
  const request = useQuery({
    queryKey: ["cli-approval", auth.user?.id, code],
    queryFn: () =>
      api<{ name: string; scopes: string[]; expires_at: string }>(
        "/cli/device/" + code,
      ),
    enabled: !!auth.user && valid,
    retry: false,
  });
  const decision = useMutation({
    mutationFn: (approve: boolean) =>
      post<{ message: string }>(`/cli/device/${code}/approve`, { approve }),
  });
  return (
    <main className="page cli-authorization">
      <Brand />
      <h1>Connect your command line.</h1>
      {auth.loading ? (
        <Loading />
      ) : auth.error ? (
        <ErrorNotice error={auth.error} />
      ) : !auth.user ? (
        <>
          <p>Sign in to review this CLI request.</p>
          <Link
            className="button primary"
            to={`/login?next=${encodeURIComponent("/cli/authorize?code=" + code)}`}
          >
            Sign in to GraphPilot
          </Link>
        </>
      ) : !valid ? (
        <p className="notice">
          This CLI link is incomplete. Run the login command again in your
          terminal.
        </p>
      ) : decision.data ? (
        <p className="notice" role="status">
          {decision.data.message}
        </p>
      ) : (
        <>
          <p>Approve only if you just ran the GraphPilot login command.</p>
          <p className="cli-user-code">
            {code.slice(0, 4)}–{code.slice(4)}
          </p>
          {request.isPending ? (
            <Loading />
          ) : request.error ? (
            <ErrorNotice error={request.error} />
          ) : (
            request.data && (
              <>
                <p>
                  <strong>{request.data.name}</strong> will connect as{" "}
                  <strong>{auth.user.email}</strong>.
                </p>
                <ul>
                  <li>Read repositories and source you can access.</li>
                  {request.data.scopes.includes("repositories:write") && (
                    <li>
                      Connect repositories, upload source and request indexing
                      or history sync.
                    </li>
                  )}
                </ul>
                <p>
                  Access expires in seven days. You can revoke it in Settings.
                  It cannot administer users or run shell commands.
                </p>
                {decision.error && <ErrorNotice error={decision.error} />}
                <div className="github-account-actions">
                  <button
                    className="button primary"
                    disabled={decision.isPending}
                    onClick={() => decision.mutate(true)}
                  >
                    Approve CLI
                  </button>
                  <button
                    className="button"
                    disabled={decision.isPending}
                    onClick={() => decision.mutate(false)}
                  >
                    Deny
                  </button>
                </div>
              </>
            )
          )}
        </>
      )}
      <p>
        <Link to="/workspace">Back to workspace</Link>
      </p>
    </main>
  );
}

export function CliCredentials() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const tokens = useQuery({
    queryKey: ["cli-credentials", user?.id],
    queryFn: () =>
      api<
        {
          id: string;
          name: string;
          scopes: string[];
          expires_at: string;
          revoked: boolean;
        }[]
      >("/cli/tokens"),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api("/cli/tokens/" + id, { method: "DELETE" }),
    onSuccess: () =>
      cache.invalidateQueries({ queryKey: ["cli-credentials", user?.id] }),
  });
  return (
    <section>
      <h2>CLI & agent access</h2>
      <p>
        Review credentials that can access your repositories. Secrets are shown
        only once to the requesting client.
      </p>
      {tokens.isPending ? (
        <Loading />
      ) : tokens.error ? (
        <ErrorNotice error={tokens.error} />
      ) : !tokens.data?.length ? (
        <p>No CLI or agent credentials have been issued.</p>
      ) : (
        <ul className="cli-credential-list">
          {tokens.data.map((t) => (
            <li key={t.id}>
              <div>
                <strong>{t.name}</strong>
                <p>
                  {t.scopes.includes("repositories:write")
                    ? "Read & manage repositories"
                    : "Read only"}{" "}
                  · Expires {date(t.expires_at)}
                </p>
              </div>
              <button
                className="button"
                disabled={t.revoked || revoke.isPending}
                onClick={() => revoke.mutate(t.id)}
              >
                {t.revoked ? "Revoked" : "Revoke"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {revoke.error && <ErrorNotice error={revoke.error} />}
    </section>
  );
}
