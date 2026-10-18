import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  Boxes,
  FolderGit2,
  GitCommitHorizontal,
  Network,
  Search,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { api, date, number, scoped, type Node, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  Branch,
  ConnectLink,
  Empty,
  ErrorNotice,
  Heading,
  Loading,
  Status,
} from "../components/ui";
export function Dashboard() {
  const { user } = useAuth();
  const location = useLocation();
  const verificationEmailSent = (
    location.state as { verificationEmailSent?: boolean | null } | null
  )?.verificationEmailSent ?? null;
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api<Repo[]>("/repositories"),
    refetchInterval: 5000,
  });
  const activity = useQuery({
    queryKey: ["activity"],
    queryFn: () =>
      api<{ id: string; action: string; created_at: string }[]>("/activity"),
  });
  const recent = useQuery({
    queryKey: ["workspace-recent"],
    queryFn: () =>
      api<{
        queries: {
          id: string;
          question: string;
          repository_id: string;
          repository_name: string;
          branch: string;
          snapshot_id: string | null;
          created_at: string;
        }[];
        failures: {
          node: Node;
          repository_id: string;
          repository_name: string;
          branch: string;
          snapshot_id: string;
        }[];
        warnings: string[];
        coverage: string;
      }>("/workspace/recent"),
    refetchInterval: 30000,
  });
  if (query.isPending) return <Loading />;
  if (query.error)
    return (
      <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    );
  const repos = query.data;
  const shown = repos.filter((r) =>
    r.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="page dashboard">
      <Heading
        title="Your code, connected."
        description={`Welcome back, ${user?.name.split(" ")[0]}. Pick a repository and follow the connections.`}
        action={<ConnectLink />}
      />
      {verificationEmailSent !== null && (
        <p className="notice" role="status">
          {verificationEmailSent
            ? "Account created. Check your inbox to verify your email."
            : "Account created, but the verification email could not be sent. You can request another from Settings."}
        </p>
      )}
      <div className="workspace-summary">
        <div>
          <FolderGit2 size={19} />
          <strong>{repos.length}</strong>
          <span>repositories</span>
        </div>
        <div>
          <Network size={19} />
          <strong>
            {number(
              repos.reduce((s, r) => s + (Number(r.stats.nodes) || 0), 0),
            )}
          </strong>
          <span>indexed entities</span>
        </div>
        <div>
          <Boxes size={19} />
          <strong>
            {
              repos.filter((r) =>
                ["indexing", "syncing", "pending"].includes(r.status),
              ).length
            }
          </strong>
          <span>repositories awaiting work</span>
        </div>
      </div>
      <section aria-labelledby="repositories-title">
        <div className="section-heading">
          <h2 id="repositories-title">
            Repositories <span className="count">{repos.length}</span>
          </h2>
          {repos.length > 0 && (
            <div className="search-input">
              <Search size={16} />
              <input
                aria-label="Filter repositories"
                placeholder="Find a repository…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          )}
        </div>
        {!repos.length ? (
          <Empty
            title="Every connection starts with a repository."
            action={<ConnectLink />}
          >
            Add a public GitHub project or upload a source archive. GraphPilot
            builds the graph from the actual source.
            <span className="empty-cli-hint">
              Prefer the terminal? Sign in with the CLI, then run{" "}
              <code>graphpilot repos connect &lt;github-url&gt;</code>.{" "}
              <Link className="empty-tools-link" to="/tools">
                Set up the CLI
              </Link>
            </span>
          </Empty>
        ) : !shown.length ? (
          <Empty title="No matching repositories">
            Try another repository name.
          </Empty>
        ) : (
          <div className="repo-grid">
            {shown.map((repo) => (
              <article className="repo-card" key={repo.id}>
                <div className="repo-card-top">
                  <span className="repo-icon">
                    <FolderGit2 size={23} strokeWidth={1.4} />
                  </span>
                  <Status status={repo.status} />
                </div>
                <h3>
                  <Link to={`/repositories/${repo.id}`} className="repo-title">
                    {repo.name}
                    <ArrowUpRight size={18} />
                  </Link>
                </h3>
                <p className="repo-source">
                  {repo.source_url?.replace("https://github.com/", "") ||
                    {
                      local: "Server-local Git",
                      archive: "Uploaded source archive",
                    }[repo.source_type]}
                </p>
                <div className="repo-card-stats">
                  <span>
                    <strong>{number(repo.stats.files)}</strong> files
                  </span>
                  <span>
                    <strong>{number(repo.stats.functions)}</strong> functions
                  </span>
                  <span>
                    <strong>{number(repo.stats.edges)}</strong> relationships
                  </span>
                </div>
                <div className="repo-card-footer">
                  <Branch name={repo.branch} />
                  <span title={repo.commit_sha ?? undefined}>
                    <GitCommitHorizontal size={13} />
                    {repo.commit_sha?.slice(0, 7) || "Not indexed yet"}
                  </span>
                  <span>
                    {repo.indexed_at
                      ? "Indexed " + date(repo.indexed_at)
                      : "Waiting for first index"}
                  </span>
                </div>
                <div className="repo-card-actions">
                  <Link to={`/repositories/${repo.id}`}>Ask</Link>
                  <Link to={`/repositories/${repo.id}/code`}>Graph</Link>
                  <Link to={`/repositories/${repo.id}/activity`}>History</Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      <div className="dashboard-bottom workspace-recent">
        <section aria-labelledby="recent-queries-title">
          <div className="section-heading">
            <h2 id="recent-queries-title">Recent queries</h2>
          </div>
          {recent.isPending ? (
            <Loading label="Loading recent queries…" />
          ) : recent.error ? (
            <ErrorNotice
              error={recent.error}
              retry={() => void recent.refetch()}
            />
          ) : !recent.data.queries.length ? (
            <p className="muted">Your repository questions will appear here.</p>
          ) : (
            <div className="workspace-evidence-list">
              {recent.data.queries.map((q) => (
                <Link
                  key={q.id}
                  to={scoped(`/repositories/${q.repository_id}/context`, q)}
                >
                  <strong>{q.question}</strong>
                  <span>
                    {q.repository_name} · {q.branch}
                  </span>
                  <time>{date(q.created_at)}</time>
                </Link>
              ))}
            </div>
          )}
        </section>
        <section aria-labelledby="ci-failures-title">
          <div className="section-heading">
            <h2 id="ci-failures-title">Recent CI failures</h2>
          </div>
          {recent.isPending ? (
            <Loading label="Loading CI history…" />
          ) : recent.error ? (
            <ErrorNotice error={recent.error} />
          ) : (
            <>
              {recent.data.failures.length ? (
                <div className="workspace-evidence-list">
                  {recent.data.failures.map((f) => (
                    <Link
                      key={`${f.snapshot_id}:${f.node.id}`}
                      to={scoped(
                        `/repositories/${f.repository_id}?node=${encodeURIComponent(f.node.id)}`,
                        f,
                      )}
                    >
                      <strong>{f.node.name}</strong>
                      <span>
                        {f.repository_name} · {f.branch}
                      </span>
                      <time>{date(f.node.timestamp)}</time>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="muted">
                  No failures found in the connected CI history.
                </p>
              )}
              {recent.data.warnings.map((w) => (
                <p className="notice" key={w}>
                  {w}
                </p>
              ))}
              <p className="workspace-coverage">{recent.data.coverage}</p>
            </>
          )}
        </section>
      </div>
      <div className="dashboard-bottom">
        <section>
          <div className="section-heading">
            <h2>Recent activity</h2>
            <Link className="text-link" to="/activity">
              View all <ArrowRight size={14} />
            </Link>
          </div>
          {activity.isPending ? (
            <Loading label="Loading activity…" />
          ) : activity.error ? (
            <ErrorNotice error={activity.error} />
          ) : !activity.data?.length ? (
            <p className="muted">Workspace activity will appear here.</p>
          ) : (
            <div className="activity-list">
              {activity.data.slice(0, 4).map((a) => (
                <div key={a.id}>
                  <span className="activity-mark" />
                  <span>
                    {a.action.split(".").join(" · ").replaceAll("_", " ")}
                  </span>
                  <time>{date(a.created_at)}</time>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="workspace-guide">
          <h2>Let the graph guide you.</h2>
          <p>
            Find a symbol. Trace its callers. Open the source. Every step gives
            you something concrete to check.
          </p>
          <Link className="text-link" to="/connect">
            Start with a repository <ArrowRight size={15} />
          </Link>
          <Network className="guide-network" size={92} strokeWidth={0.7} />
        </section>
      </div>
    </div>
  );
}
