import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { api, date, type Job, type Repo, type User } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ErrorNotice, Heading, Loading, Status } from "../components/ui";
export function Admin() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [tab, setTab] = useState("users");
  const [repo, setRepo] = useState("");
  const [member, setMember] = useState("");
  const [permission, setPermission] = useState("read");
  const [newOwner, setNewOwner] = useState("");
  const [previousAccess, setPreviousAccess] = useState("read");
  const query = useQuery({
    queryKey: ["admin", tab],
    queryFn: () => api<unknown[]>("/admin/" + tab),
    enabled: tab !== "health" && tab !== "configuration",
    refetchInterval: 5000,
  });
  const health = useQuery({
    queryKey: ["admin-health"],
    queryFn: () => api<{ checks: Record<string, string> }>("/health/ready"),
    enabled: tab === "health",
    refetchInterval: 5000,
  });
  const metrics = useQuery({
    queryKey: ["admin-metrics"],
    queryFn: () => api<Metrics>("/admin/metrics"),
    enabled: tab === "health",
    refetchInterval: 5000,
  });
  const configuration = useQuery({
    queryKey: ["admin-config"],
    queryFn: () => api<Configuration>("/admin/config"),
    enabled: tab === "configuration",
  });
  const repos = useQuery({
    queryKey: ["admin-repositories"],
    queryFn: () => api<Repo[]>("/admin/repositories"),
  });
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<User[]>("/admin/users"),
    refetchInterval: tab === "repositories" ? 5000 : false,
  });
  const members = useQuery({
    queryKey: ["admin-members", repo],
    queryFn: () =>
      api<{ user_id: string; email: string; permission: string }[]>(
        "/admin/repositories/" + repo + "/members",
      ),
    enabled: !!repo,
  });
  const action = useMutation({
    mutationFn: ({
      path,
      method = "POST",
      body,
    }: {
      path: string;
      method?: string;
      body?: unknown;
    }) => api(path, { method, body: body ? JSON.stringify(body) : undefined }),
    onSuccess: (result) => {
      if (typeof result === "object" && result !== null && "owner_id" in result)
        setNewOwner("");
      void cache.invalidateQueries({ queryKey: ["admin"] });
      void cache.invalidateQueries({ queryKey: ["admin-members"] });
      void cache.invalidateQueries({ queryKey: ["admin-users"] });
      void cache.invalidateQueries({ queryKey: ["admin-repositories"] });
    },
  });
  if (user?.role !== "admin") return <Navigate to="/workspace" replace />;
  return (
    <div className="page admin-page">
      <Heading
        title="Workspace administration"
        description="Manage accounts and repository access. Sensitive actions are recorded in the audit log."
      />
      <div
        className="admin-tabs"
        role="group"
        aria-label="Administration views"
      >
        {[
          "users",
          "repositories",
          "jobs",
          "audit",
          "health",
          "configuration",
        ].map((t) => (
          <button
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t === "health" ? "System health" : t}
          </button>
        ))}
      </div>
      {action.error && <ErrorNotice error={action.error} />}{" "}
      {action.isSuccess && (
        <p className="notice subtle" role="status">
          Change saved.
        </p>
      )}
      {tab === "configuration" ? (
        configuration.isPending ? (
          <Loading />
        ) : configuration.error ? (
          <ErrorNotice
            error={configuration.error}
            retry={() => void configuration.refetch()}
          />
        ) : (
          <LogPolicyForm configuration={configuration.data} />
        )
      ) : tab === "health" ? (
        health.isPending ? (
          <Loading />
        ) : health.error ? (
          <ErrorNotice error={health.error} />
        ) : (
          <>
            <h2>Live database connectivity</h2>
            <dl className="definition-list">
              {Object.entries(health.data?.checks || {}).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            <p className="notice subtle">
              Readiness confirms current database connectivity. It does not
              certify security, backup freshness or worker availability.
            </p>
            {metrics.isPending ? (
              <Loading label="Measuring system diagnostics…" />
            ) : metrics.error ? (
              <ErrorNotice
                error={metrics.error}
                retry={() => void metrics.refetch()}
              />
            ) : (
              metrics.data && <SystemMetrics data={metrics.data} />
            )}
          </>
        )
      ) : query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorNotice error={query.error} />
      ) : (
        <div className="table-wrap">
          {tab === "users" ? (
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Role</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {(query.data as User[]).map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.name}</strong>
                      <small>{u.email}</small>
                    </td>
                    <td>
                      <select
                        aria-label={"Role for " + u.email}
                        value={u.role}
                        disabled={u.id === user.id || action.isPending}
                        onChange={(e) =>
                          action.mutate({
                            path: "/admin/users/" + u.id,
                            method: "PATCH",
                            body: { role: e.target.value },
                          })
                        }
                      >
                        <option value="user">User</option>
                        <option value="admin">Admin</option>
                      </select>
                    </td>
                    <td>
                      <button
                        className="button secondary small-button"
                        disabled={u.id === user.id || action.isPending}
                        onClick={() =>
                          action.mutate({
                            path: "/admin/users/" + u.id,
                            method: "PATCH",
                            body: { disabled: !u.disabled },
                          })
                        }
                      >
                        {u.disabled ? "Enable account" : "Disable account"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : tab === "repositories" ? (
            <table>
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Branch</th>
                  <th>Status</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {(query.data as Repo[]).map((r) => (
                  <tr key={r.id}>
                    <td>{r.name}</td>
                    <td>{r.branch}</td>
                    <td>
                      <Status status={r.status} />
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setRepo(r.id)}
                      >
                        Manage members
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : tab === "jobs" ? (
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {(query.data as Job[]).map((j) => (
                  <tr key={j.id}>
                    <td>
                      {j.kind}
                      <small>
                        {j.id.slice(0, 8)} · {date(j.created_at)}
                      </small>
                    </td>
                    <td>
                      <Status status={j.status} />
                    </td>
                    <td>{j.progress}%</td>
                    <td>
                      {["failed", "cancelled"].includes(j.status) && (
                        <button
                          className="text-button"
                          disabled={action.isPending}
                          onClick={() =>
                            action.mutate({
                              path: "/admin/jobs/" + j.id + "/retry",
                            })
                          }
                        >
                          Retry job
                        </button>
                      )}
                      {["queued", "running"].includes(j.status) &&
                        j.kind !== "delete" && (
                          <button
                            className="text-button"
                            disabled={action.isPending || j.cancel_requested}
                            onClick={() =>
                              action.mutate({
                                path: "/admin/jobs/" + j.id + "/cancel",
                              })
                            }
                          >
                            {j.cancel_requested
                              ? "Cancellation requested"
                              : "Cancel job"}
                          </button>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Target</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {(
                  query.data as {
                    id: string;
                    action: string;
                    user_id: string;
                    target: string;
                    created_at: string;
                  }[]
                ).map((a) => (
                  <tr key={a.id}>
                    <td>{a.action}</td>
                    <td>
                      <code>{a.user_id?.slice(0, 8) || "Anonymous"}</code>
                    </td>
                    <td>
                      <code>{a.target.slice(0, 36)}</code>
                    </td>
                    <td>{date(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {tab === "repositories" && repo && (
        <section className="access-panel">
          <h2>Repository access</h2>
          <p>
            Grants take effect on the backend. Admins need an explicit, audited
            membership to read repository content.
          </p>
          {members.isPending ? (
            <Loading />
          ) : members.error ? (
            <ErrorNotice error={members.error} />
          ) : (
            members.data?.map((m) => (
              <div className="member-row" key={m.user_id}>
                <span>{m.email}</span>
                <strong>{m.permission}</strong>
                {m.permission !== "owner" && (
                  <button
                    className="text-button"
                    disabled={action.isPending}
                    onClick={() =>
                      action.mutate({
                        path: `/admin/repositories/${repo}/members/${m.user_id}`,
                        method: "DELETE",
                      })
                    }
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
          <form
            className="grant-form"
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({
                path: `/admin/repositories/${repo}/members/${member}`,
                method: "PUT",
                body: { permission },
              });
            }}
          >
            {users.error && (
              <ErrorNotice
                error={users.error}
                retry={() => void users.refetch()}
              />
            )}
            <label>
              Account
              <select
                aria-label="Account"
                required
                value={member}
                onChange={(e) => setMember(e.target.value)}
              >
                <option value="">Choose account</option>
                {users.data?.map((u) => (
                  <option value={u.id} key={u.id}>
                    {u.email}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Permission
              <select
                aria-label="Permission"
                value={permission}
                onChange={(e) => setPermission(e.target.value)}
              >
                <option value="read">Read</option>
                <option value="write">Write</option>
              </select>
            </label>
            <button
              className="button primary"
              disabled={!member || action.isPending}
            >
              Grant access
            </button>
          </form>
          <label>
            Choose repository
            <select
              aria-label="Choose repository"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
            >
              {repos.data?.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
          <h2 className="ownership-title">Transfer repository ownership</h2>
          <p>
            Current owner:{" "}
            <strong>
              {members.data?.find((m) => m.permission === "owner")?.email ||
                "Loading…"}
            </strong>
            . Choose the receiving account and the previous owner’s access.
          </p>
          <form
            className="grant-form"
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({
                path: `/admin/repositories/${repo}/ownership`,
                body: {
                  new_owner_id: newOwner,
                  previous_owner_access: previousAccess,
                },
              });
            }}
          >
            <label>
              New owner
              <select
                aria-label="New owner"
                value={newOwner}
                onChange={(e) => setNewOwner(e.target.value)}
                required
              >
                <option value="">Choose enabled account</option>
                {users.data
                  ?.filter(
                    (u) =>
                      !u.disabled &&
                      !members.data?.some(
                        (m) => m.user_id === u.id && m.permission === "owner",
                      ),
                  )
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.email}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Previous owner access
              <select
                aria-label="Previous owner access"
                value={previousAccess}
                onChange={(e) => setPreviousAccess(e.target.value)}
              >
                <option value="read">Read</option>
                <option value="write">Write</option>
                <option value="remove">Remove access</option>
              </select>
            </label>
            <button
              className="button secondary"
              disabled={!newOwner || action.isPending}
            >
              Transfer ownership
            </button>
          </form>
        </section>
      )}
    </div>
  );
}

type Configuration = {
  values: {
    artifact_retention_days: number;
    max_log_downloads: number;
    max_log_bytes: number;
  };
  application_delay_seconds: number;
  scope: string;
};
function LogPolicyForm({ configuration }: { configuration: Configuration }) {
  const cache = useQueryClient();
  const save = useMutation({
    mutationFn: (values: Configuration["values"]) =>
      api<Configuration>("/admin/config", {
        method: "PUT",
        body: JSON.stringify(values),
      }),
    onSuccess: (result) => cache.setQueryData(["admin-config"], result),
  });
  return (
    <section className="access-panel log-policy">
      <h2>CI log archive policy</h2>
      <p>
        Set limits for newly downloaded logs. Existing archives retain their
        original expiration. Workers observe saved changes within{" "}
        {configuration.application_delay_seconds} seconds.
      </p>
      <form
        className="policy-form"
        onSubmit={(e) => {
          e.preventDefault();
          const fields = new FormData(e.currentTarget);
          save.mutate({
            artifact_retention_days: Number(fields.get("retention")),
            max_log_downloads: Number(fields.get("downloads")),
            max_log_bytes: Number(fields.get("bytes")),
          });
        }}
      >
        <label>
          Retain new log archives (days)
          <input
            name="retention"
            type="number"
            min={1}
            max={3650}
            required
            defaultValue={configuration.values.artifact_retention_days}
          />
        </label>
        <label>
          New log downloads per sync
          <input
            name="downloads"
            aria-label="New log downloads per sync"
            aria-describedby="log-download-help"
            type="number"
            min={0}
            max={30}
            required
            defaultValue={configuration.values.max_log_downloads}
          />
          <small id="log-download-help">
            Use 0 to disable new log downloads.
          </small>
        </label>
        <label>
          Maximum log size (bytes)
          <input
            name="bytes"
            type="number"
            min={1000}
            max={10000000}
            required
            defaultValue={configuration.values.max_log_bytes}
          />
        </label>
        <button className="button primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save log policy"}
        </button>
      </form>
      {save.error && <ErrorNotice error={save.error} />}
      {save.isSuccess && (
        <p className="notice subtle" role="status">
          Log policy saved. The change is recorded in the audit log.
        </p>
      )}
    </section>
  );
}

type Metrics = {
  requests: {
    scope: string;
    requests_since_start: number;
    application_errors_since_start: number;
    p50_ms: number | null;
    p95_ms: number | null;
    api_peak_rss_mib: number;
    graph_reads: {
      samples: number;
      p50_ms: number | null;
      p95_ms: number | null;
      errors: number;
      scope: string;
    };
  };
  postgres_bytes: number;
  artifacts: {
    bytes: Record<string, number | null>;
    complete: boolean;
    measured_at: string;
    scope: string;
  };
  workers: {
    worker_id: string;
    status: string;
    observation: string;
    last_seen: string;
    active_job_id: string | null;
  }[];
};
function SystemMetrics({ data }: { data: Metrics }) {
  const ms = (value: number | null) =>
    value === null ? "No samples" : `${value} ms`;
  const mib = (value: number | null) =>
    value === null ? "Unavailable" : `${(value / 1048576).toFixed(2)} MiB`;
  return (
    <>
      <div className="diagnostics-grid">
        <section>
          <h2>Request observations</h2>
          <dl className="definition-list">
            {[
              ["Requests since restart", data.requests.requests_since_start],
              [
                "Application errors",
                data.requests.application_errors_since_start,
              ],
              ["API request p50", ms(data.requests.p50_ms)],
              ["API request p95", ms(data.requests.p95_ms)],
              ["Graph read p50", ms(data.requests.graph_reads.p50_ms)],
              ["Graph read p95", ms(data.requests.graph_reads.p95_ms)],
              ["Graph read errors", data.requests.graph_reads.errors],
              ["API peak memory", `${data.requests.api_peak_rss_mib} MiB`],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="notice subtle">
            {data.requests.scope}. Graph timings cover{" "}
            {data.requests.graph_reads.samples} reads in this API process.
          </p>
        </section>
        <section>
          <h2>Measured storage</h2>
          <dl className="definition-list">
            <div>
              <dt>PostgreSQL database</dt>
              <dd>{mib(data.postgres_bytes)}</dd>
            </div>
            {Object.entries(data.artifacts.bytes).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{mib(v)}</dd>
              </div>
            ))}
          </dl>
          <p className="notice subtle">
            {data.artifacts.scope}.{" "}
            {data.artifacts.complete ? "Scan completed" : "Partial scan"} ·{" "}
            {date(data.artifacts.measured_at)}.
          </p>
        </section>
      </div>
      <h2>Worker observations</h2>
      {data.workers.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Worker</th>
                <th>State</th>
                <th>Last observed</th>
                <th>Job</th>
              </tr>
            </thead>
            <tbody>
              {data.workers.map((w) => (
                <tr key={w.worker_id}>
                  <td>
                    <code>{w.worker_id.slice(0, 8)}</code>
                  </td>
                  <td>
                    {w.observation} · {w.status}
                  </td>
                  <td>{date(w.last_seen)}</td>
                  <td>{w.active_job_id?.slice(0, 8) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No worker heartbeat has been recorded.</p>
      )}
      <p className="notice subtle">
        Workers report every 10 seconds. Observations older than 45 seconds are
        stale; recent presence does not certify successful job completion.
      </p>
    </>
  );
}
