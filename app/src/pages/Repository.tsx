import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  FileCode2,
  GitCommitHorizontal,
  GitPullRequest,
  History,
  Network,
  RefreshCw,
  Search,
  Waypoints,
  X,
} from "lucide-react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { lazy, Suspense, useMemo, useState } from "react";
import {
  api,
  date,
  number,
  post,
  safeUrl,
  scoped,
  type Branches,
  type ContentSearch,
  type Snapshot,
  type Evidence,
  type Graph,
  type ImpactResult,
  type Job,
  type Node,
  type Repo,
} from "../lib/api";
import {
  Branch,
  Empty,
  ErrorNotice,
  Heading,
  Loading,
  Status,
} from "../components/ui";
const GraphCanvas = lazy(() =>
  import("../components/GraphCanvas").then((m) => ({ default: m.GraphCanvas })),
);
import { ContextExplorer } from "./context";
export function RepositoryPage({ view = "context" }: { view?: string }) {
  const { id } = useParams();
  const base = `/repositories/${id}`;
  const [params, setParams] = useSearchParams();
  const branch = params.get("branch");
  const revision = params.get("revision");
  const section =
    ["graph", "code", "impact"].includes(view) || params.has("node")
      ? "code"
      : ["overview", "history", "diagnostics", "activity"].includes(view)
        ? "activity"
        : "ask";
  const tab = view === "impact" ? "impact" : section;
  const selectedContext = { branch, revision };
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["repository", id, branch, revision],
    queryFn: () => api<Repo>(scoped(base, selectedContext)),
    refetchInterval: 3000,
  });
  const jobs = useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api<Job[]>(base + "/jobs"),
    refetchInterval: 2000,
  });
  const enqueue = useMutation({
    mutationFn: (kind: string) =>
      post(scoped(base + "/jobs?kind=" + kind, { branch })),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["jobs", id] });
      void query.refetch();
    },
  });
  if (query.isPending) return <Loading label="Opening repository…" />;
  if (query.error)
    return (
      <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    );
  const repo = query.data;
  const active = jobs.data?.find((j) =>
    ["queued", "running"].includes(j.status),
  );
  const selectedJobs =
    jobs.data?.filter((j) => !j.branch || j.branch === repo.branch) || [];
  const lastJob = selectedJobs[0];
  const locked = !!revision || repo.permission === "read";
  const generation = `${repo.id}:${repo.branch}:${repo.snapshot_id || repo.commit_sha}`;
  return (
    <div className="page repository-page">
      <Link className="back-link" to="/workspace">
        <ArrowLeft size={14} />
        Repositories
      </Link>
      <div className="repository-heading">
        <div>
          <div className="repo-title-line">
            <h1>{repo.name}</h1>
            <Branch name={repo.branch} />
            <Status status={repo.status} />
          </div>
          <p>
            {repo.source_url ? (
              <a
                href={safeUrl(repo.source_url)}
                target="_blank"
                rel="noreferrer"
              >
                {repo.source_url.replace("https://github.com/", "")}
                <ExternalLink size={12} />
              </a>
            ) : repo.source_type === "local" ? (
              "Server-local Git repository"
            ) : (
              "Uploaded source snapshot"
            )}
            <span className="inline-divider" />
            <GitCommitHorizontal size={14} />
            {repo.commit_sha?.slice(0, 8) || "No indexed commit"}
            <span className="inline-divider" />
            {date(repo.indexed_at)}
          </p>
        </div>
        <button
          className="button secondary"
          disabled={locked || !!active || enqueue.isPending}
          onClick={() => enqueue.mutate("index")}
        >
          <RefreshCw size={15} className={active ? "spin" : ""} />
          {active ? "Job in progress" : "Sync source"}
        </button>
      </div>
      <details className="repository-options" open={!!branch || !!revision}>
        <summary>Branch & saved versions</summary>
        <BranchControls
          repo={repo}
          revision={revision}
          busy={!!active}
          select={(branch, revision) => {
            const next = new URLSearchParams();
            next.set("branch", branch);
            if (revision) next.set("revision", revision);
            setParams(next);
          }}
        />
      </details>
      {revision && (
        <p className="notice subtle">
          Viewing a saved snapshot. Source and graph evidence stay at this
          revision. Select “Latest indexed” to sync.
        </p>
      )}
      <nav className="repo-tabs" aria-label="Repository navigation">
        {[
          ["ask", "Ask", ""],
          ["code", "Graph", "/code"],
          ["impact", "Impact", "/impact"],
          ["activity", "History", "/activity"],
        ].map(([key, label, path]) => (
          <Link
            key={key}
            className={tab === key ? "active" : undefined}
            aria-current={tab === key ? "page" : undefined}
            to={scoped(base + path, selectedContext)}
          >
            {label}
          </Link>
        ))}
      </nav>
      {enqueue.error && <ErrorNotice error={enqueue.error} />}{" "}
      {active && (
        <div className="job-progress" role="status">
          <div>
            <span className="live-dot" />
            <strong>
              {active.kind === "index"
                ? "Indexing repository"
                : "Synchronizing history"}
            </strong>
            <span>{active.progress}%</span>
          </div>
          <progress max={100} value={active.progress} />
          <p>{active.message}</p>
        </div>
      )}
      {!repo.commit_sha ? (
        <>
          {lastJob?.status === "failed" && (
            <ErrorNotice error={new Error(lastJob.message)} />
          )}
          <Empty
            title={
              active
                ? "Building your repository graph."
                : "Your graph is waiting for its first index."
            }
          >
            {active
              ? "The durable worker is reading your source and resolving static relationships. Progress updates appear here."
              : "Start an index to create real graph entities and source references."}
          </Empty>
        </>
      ) : section === "ask" ? (
        <ContextExplorer key={generation} repo={repo} />
      ) : section === "code" ? (
        <>
          <GraphExplorer key={generation} repo={repo} />
          <details className="repository-detail" open={view === "impact"}>
            <summary>Trace dependencies</summary>
            <Impact key={generation} repo={repo} />
          </details>
        </>
      ) : (
        <>
          <Timeline
            repo={repo}
            sync={() => enqueue.mutate("github-sync")}
            busy={locked || !!active || enqueue.isPending}
          />
          <details className="repository-detail" open={view === "overview"}>
            <summary>Repository details & indexing jobs</summary>
            <Overview repo={repo} jobs={selectedJobs} />
          </details>
          <details className="repository-detail" open={view === "diagnostics"}>
            <summary>Index health</summary>
            <Diagnostics repo={repo} jobs={selectedJobs} />
          </details>
        </>
      )}
    </div>
  );
}
function BranchControls({
  repo,
  revision,
  busy,
  select,
}: {
  repo: Repo;
  revision: string | null;
  busy: boolean;
  select: (branch: string, revision?: string) => void;
}) {
  const cache = useQueryClient();
  const [name, setName] = useState("");
  const base = "/repositories/" + repo.id;
  const branches = useQuery({
    queryKey: ["branches", repo.id, repo.status],
    queryFn: () => api<Branches>(base + "/branches"),
  });
  const snapshots = useQuery({
    queryKey: ["snapshots", repo.id, repo.branch, repo.snapshot_id],
    queryFn: () =>
      api<Snapshot[]>(scoped(base + "/snapshots", { branch: repo.branch })),
  });
  const connect = useMutation({
    mutationFn: () => post(base + "/branches", { branch: name.trim() }),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["branches", repo.id] });
      void cache.invalidateQueries({ queryKey: ["jobs", repo.id] });
      select(name.trim());
      setName("");
    },
  });
  return (
    <>
      <div className="repository-context">
        <label>
          Branch
          <select
            aria-label="Branch"
            value={repo.branch}
            onChange={(e) => select(e.target.value)}
            disabled={branches.isPending}
          >
            {(
              branches.data?.branches || [
                { branch: repo.branch, status: repo.status },
              ]
            ).map((b) => (
              <option key={b.branch} value={b.branch}>
                {b.branch}
                {b.status === "failed" ? " (index failed)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Snapshot
          <select
            aria-label="Snapshot"
            value={revision || ""}
            onChange={(e) => select(repo.branch, e.target.value)}
            disabled={snapshots.isPending}
          >
            <option value="">Latest indexed</option>
            {revision && !snapshots.data?.some((s) => s.id === revision) && (
              <option value={revision}>
                Selected saved snapshot · {repo.commit_sha?.slice(0, 8)}
              </option>
            )}
            {snapshots.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.commit_sha.slice(0, 8)} · {date(s.created_at)} ·{" "}
                {s.kind === "index" ? "Source" : "History"}
                {s.current ? " (current)" : ""}
              </option>
            ))}
          </select>
        </label>
        {repo.source_type !== "archive" &&
          repo.permission !== "read" &&
          !revision && (
            <details className="connect-branch">
              <summary>Connect branch</summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  connect.mutate();
                }}
              >
                <label>
                  Existing Git branch
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="feature/auth"
                    maxLength={200}
                    required
                  />
                </label>
                <button
                  className="button secondary small-button"
                  disabled={busy || connect.isPending || !name.trim()}
                >
                  {connect.isPending ? "Connecting…" : "Connect & index branch"}
                </button>
              </form>
            </details>
          )}
      </div>
      {branches.error && (
        <ErrorNotice
          error={branches.error}
          retry={() => void branches.refetch()}
        />
      )}
      {snapshots.error && (
        <ErrorNotice
          error={snapshots.error}
          retry={() => void snapshots.refetch()}
        />
      )}
      {connect.error && <ErrorNotice error={connect.error} />}
    </>
  );
}
function GraphExplorer({ repo }: { repo: Repo }) {
  const read = <T,>(path: string) => api<T>(scoped(path, repo));
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [kind, setKind] = useState("");
  const [relation, setRelation] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const mode = params.get("mode") === "content" ? "content" : "symbols";
  const around = params.get("around");
  const column = params.get("column");
  const endColumn = params.get("end_column");
  const [expanded, setExpanded] = useState<Graph>({
    nodes: [],
    edges: [],
    limit: 80,
    bounded: true,
  });
  const base = "/repositories/" + repo.id;
  const selected = params.get("node") || "";
  const query = useQuery({
    queryKey: [
      "graph",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      repo.commit_sha,
      repo.sync_state.last_synced_at,
      term,
      kind,
      relation,
    ],
    queryFn: () =>
      read<Graph>(
        base +
          "/graph?limit=80&q=" +
          encodeURIComponent(term) +
          "&kind=" +
          kind +
          "&relation=" +
          relation,
      ),
    enabled: mode === "symbols",
  });
  const selectedQuery = useQuery({
    queryKey: [
      "node",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      selected,
      repo.commit_sha,
    ],
    queryFn: () => read<Node>(base + "/nodes/" + selected),
    enabled: !!selected,
  });
  const evidence = useQuery({
    queryKey: [
      "evidence",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      selected,
      repo.commit_sha,
      around,
      column,
      endColumn,
    ],
    queryFn: () => {
      const query = new URLSearchParams();
      if (around) query.set("around", around);
      if (column) query.set("column", column);
      if (endColumn) query.set("end_column", endColumn);
      const suffix = query.size ? "?" + query.toString() : "";
      return read<Evidence>(base + "/evidence/" + selected + suffix);
    },
    enabled: !!selected,
  });
  const content = useQuery({
    queryKey: [
      "content-search",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      term,
      matchCase,
    ],
    queryFn: () =>
      read<ContentSearch>(
        base +
          "/search/content?q=" +
          encodeURIComponent(term) +
          "&case=" +
          matchCase +
          "&limit=25",
      ),
    enabled: mode === "content" && !!term,
  });
  const expansion = useMutation({
    mutationFn: () =>
      read<Graph>(
        base + "/nodes/" + selected + "/neighbors?relation=" + relation,
      ),
    onSuccess: (result) =>
      setExpanded((previous) => ({
        nodes: [
          ...new Map(
            [...previous.nodes, ...result.nodes].map((n) => [n.id, n]),
          ).values(),
        ].slice(0, 200),
        edges: [
          ...new Map(
            [...previous.edges, ...result.edges].map((e) => [e.id, e]),
          ).values(),
        ].slice(0, 500),
        bounded: true,
        limit: 200,
      })),
  });
  const graph = useMemo(() => {
    const nodes = [
      ...new Map(
        [
          ...(query.data?.nodes || []),
          ...expanded.nodes,
          ...(selectedQuery.data ? [selectedQuery.data] : []),
        ].map((n) => [n.id, n]),
      ).values(),
    ].slice(0, 200);
    const ids = new Set(nodes.map((n) => n.id));
    return {
      nodes,
      edges: [
        ...new Map(
          [...(query.data?.edges || []), ...expanded.edges].map((e) => [
            e.id,
            e,
          ]),
        ).values(),
      ].filter((e) => ids.has(e.source) && ids.has(e.target)),
      bounded: true,
      limit: 200,
    };
  }, [query.data, expanded, selectedQuery.data]);
  function select(node: Node, anchor?: number, hitColumn?: number, hitEnd?: number) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("node", node.id);
      if (anchor) next.set("around", String(anchor));
      else next.delete("around");
      if (hitColumn) next.set("column", String(hitColumn));
      else next.delete("column");
      if (hitEnd) next.set("end_column", String(hitEnd));
      else next.delete("end_column");
      return next;
    });
  }
  const evidencePanel = (
    <aside
      className="evidence-panel"
      id="source-panel"
      tabIndex={-1}
      aria-label="Node details"
    >
      {!selected ? (
        <div className="node-empty">
          <Network size={35} strokeWidth={1.2} />
          <h2>Follow a connection.</h2>
          <p>
            Select a node to inspect its source, relationships and provenance.
          </p>
          <span>Pan to explore · Scroll to zoom</span>
        </div>
      ) : selectedQuery.isPending ? (
        <Loading label="Loading node…" />
      ) : selectedQuery.error ? (
        <ErrorNotice error={selectedQuery.error} />
      ) : (
        <>
          <button
            className="icon-button panel-close"
            aria-label="Clear selected node"
            onClick={() => {
              const next = new URLSearchParams(params);
              next.delete("node");
              next.delete("around");
              next.delete("column");
              next.delete("end_column");
              navigate(base + "/code" + (next.size ? "?" + next.toString() : ""));
            }}
          >
            <X size={16} />
          </button>
          <h2>{selectedQuery.data?.name}</h2>
          <p className="source-location">
            <FileCode2 size={14} />
            {selectedQuery.data?.type} ·{" "}
            {selectedQuery.data?.path || "Historical evidence"}
            {selectedQuery.data?.line && `:${selectedQuery.data.line}`}
          </p>
          {selectedQuery.data?.doc && (
            <p className="node-doc">{selectedQuery.data.doc}</p>
          )}
          {selectedQuery.data?.log_status && (
            <p className="notice subtle">{selectedQuery.data.log_status}</p>
          )}
          <div className="node-actions">
            <button
              className="button secondary small-button"
              disabled={expansion.isPending || graph.nodes.length >= 200}
              onClick={() => expansion.mutate()}
            >
              <Waypoints size={15} />
              {expansion.isPending ? "Expanding…" : "Expand neighbors"}
            </button>
            <Link
              className="text-link"
              to={scoped(base + "/impact?node=" + selected, repo)}
            >
              Analyze impact <ArrowRight size={14} />
            </Link>
            {around && (
              <Link
                className="text-link"
                to={scoped(
                  base +
                    "?pin=" +
                    selected +
                    "&line=" +
                    around +
                    (column ? "&column=" + column : "") +
                    (endColumn ? "&end_column=" + endColumn : "") +
                    "&q=" +
                    encodeURIComponent("Explain this code"),
                  repo,
                )}
              >
                Ask about this <ArrowRight size={14} />
              </Link>
            )}
          </div>
          {expansion.error && <ErrorNotice error={expansion.error} />}
          <h3>Connections in the loaded view</h3>
          <div className="connection-entries">
            {graph.edges
              .filter((e) => e.source === selected || e.target === selected)
              .map((e) => (
                <p key={e.id}>
                  <strong>{graph.nodes.find((n) => n.id === e.source)?.name}</strong>
                  <span>{e.type} →</span>
                  <strong>{graph.nodes.find((n) => n.id === e.target)?.name}</strong>
                  <small>
                    {e.source === selected ? "Outgoing" : "Incoming"}{" "}
                    {e.provenance === "github-api"
                      ? "GitHub metadata relationship"
                      : "static relationship"}
                  </small>
                </p>
              ))}
            {!graph.edges.some(
              (e) => e.source === selected || e.target === selected,
            ) && (
              <p>No connections loaded. Expand neighbors to inspect direct relationships.</p>
            )}
          </div>
          <h3>Source evidence</h3>
          {evidence.isPending ? (
            <Loading label="Reading source…" />
          ) : evidence.error ? (
            <ErrorNotice error={evidence.error} />
          ) : (
            evidence.data && (
              <>
                {evidence.data.notice && (
                  <p className="notice subtle">{evidence.data.notice}</p>
                )}
                <div className="code-block">
                  {evidence.data.content ? (
                    // A trailing LF belongs to the line it ends; it never
                    // produces an extra numbered empty line.
                    (evidence.data.content.endsWith("\n")
                      ? evidence.data.content.slice(0, -1)
                      : evidence.data.content
                    )
                      .split("\n")
                      .map((line, i) => {
                        const number = evidence.data!.start_line;
                        const hit =
                          number !== null &&
                          around !== null &&
                          number + i === Number(around);
                        const excerpt = evidence.data!.line_excerpt;
                        const partialLine =
                          excerpt && number !== null && number + i === excerpt.line
                            ? excerpt
                            : null;
                        return (
                          <div
                            className={"code-line" + (hit ? " match-line" : "")}
                            key={i}
                          >
                            <span>{number !== null ? number + i : ""}</span>
                            <code>
                              {partialLine && partialLine.start_column > 1
                                ? "…"
                                : ""}
                              {line || " "}
                              {partialLine &&
                              partialLine.end_column < partialLine.line_length
                                ? "…"
                                : ""}
                            </code>
                          </div>
                        );
                      })
                  ) : (
                    <p>No source excerpt is available for this entity.</p>
                  )}
                </div>
                {evidence.data.truncated && (
                  <p className="small muted">
                    {selectedQuery.data?.type === "LogArtifact"
                      ? "Log preview limited to 12,000 characters."
                      : "Excerpt limited to 200 lines or 12,000 characters."}
                    {evidence.data.end_line_partial
                      ? " The final line shown is cut mid-line."
                      : ""}
                  </p>
                )}
                {evidence.data.line_excerpt?.partial && (
                  <p className="small muted">
                    Line {evidence.data.line_excerpt.line} is{" "}
                    {evidence.data.line_excerpt.line_length} characters — showing
                    columns {evidence.data.line_excerpt.start_column}–
                    {evidence.data.line_excerpt.end_column} around the match.
                  </p>
                )}
                {evidence.data.download_url && evidence.data.content && (
                  <a
                    className="text-link log-download"
                    href={scoped(evidence.data.download_url, repo)}
                    download
                  >
                    Download redacted log <ArrowRight size={13} />
                  </a>
                )}
                {safeUrl(evidence.data.url) && (
                  <a
                    className="text-link"
                    href={safeUrl(evidence.data.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open source on GitHub <ExternalLink size={13} />
                  </a>
                )}
                <div className="evidence-provenance">
                  <strong>
                    {selectedQuery.data?.type === "LogArtifact"
                      ? "Redacted CI log evidence"
                      : selectedQuery.data?.provenance === "github-api"
                        ? "GitHub API evidence"
                        : "Static source evidence"}
                  </strong>
                  <p>
                    {selectedQuery.data?.type === "LogArtifact"
                      ? `Workflow commit ${evidence.data.commit.slice(0, 12)}. Archived text is subject to retention.`
                      : `Commit ${evidence.data.commit.slice(0, 12)}. Static resolution does not prove runtime behavior.`}
                  </p>
                </div>
              </>
            )
          )}
        </>
      )}
    </aside>
  );
  return (
    <>
      <div className="graph-toolbar">
        <form
          className="search-input graph-search"
          onSubmit={(e) => {
            e.preventDefault();
            setExpanded({ nodes: [], edges: [], limit: 80, bounded: true });
            setTerm(search);
          }}
        >
          <Search size={17} />
          <input
            aria-label={mode === "content" ? "Search source text" : "Search graph"}
            placeholder={
              mode === "content"
                ? "Find exact text in source…"
                : "Find a function, class or file…"
            }
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            maxLength={200}
          />
          <button
            aria-label={mode === "content" ? "Search content" : "Search symbols"}
            className="icon-button"
          >
            <ArrowRight size={17} />
          </button>
        </form>
        <label className="inline-label">
          Search
          <select
            value={mode}
            onChange={(e) => {
              setExpanded({ nodes: [], edges: [], limit: 80, bounded: true });
              setParams((previous) => {
                const next = new URLSearchParams(previous);
                if (e.target.value === "content") next.set("mode", "content");
                else next.delete("mode");
                next.delete("node");
                next.delete("around");
                next.delete("column");
                next.delete("end_column");
                return next;
              });
            }}
          >
            <option value="symbols">Symbols</option>
            <option value="content">Content</option>
          </select>
        </label>
        {mode === "content" && (
          <label className="inline-label checkbox-label">
            <input
              type="checkbox"
              checked={matchCase}
              onChange={(e) => setMatchCase(e.target.checked)}
            />
            Match case
          </label>
        )}
        {mode === "symbols" && (
          <>
            <label className="inline-label">
              Node type
              <select
                value={kind}
                onChange={(e) => {
                  setExpanded({ nodes: [], edges: [], limit: 80, bounded: true });
                  setKind(e.target.value);
                }}
              >
                <option value="">All types</option>
                {[
                  "File",
                  "Function",
                  "Class",
                  "TestCase",
                  "Commit",
                  "Issue",
                  "PullRequest",
                  "WorkflowRun",
                  "LogArtifact",
                ].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="inline-label">
              Relationship
              <select
                aria-label="Relationship type"
                value={relation}
                onChange={(e) => {
                  setExpanded({ nodes: [], edges: [], limit: 80, bounded: true });
                  setRelation(e.target.value);
                }}
              >
                <option value="">All relationships</option>
                {[
                  "CALLS",
                  "IMPORTS",
                  "DEFINES",
                  "TESTS",
                  "HAS_FILE",
                  "REFERENCES",
                  "MODIFIES",
                  "TRIGGERED_BY",
                ].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <span className="small muted graph-count">
          {mode === "content" && content.data
            ? `${content.data.returned} matches · ${content.data.scan.files_scanned} files`
            : `${graph.nodes.length} nodes loaded`}
        </span>
      </div>
      {mode === "content" ? (
        !term ? (
          <Empty title="Search the snapshot's source">
            Exact text is matched against the indexed files in this pinned
            snapshot — quote or paste the string, including punctuation.
          </Empty>
        ) : content.isPending ? (
          <Loading label="Scanning retained source…" />
        ) : content.error ? (
          <ErrorNotice
            error={content.error}
            retry={() => void content.refetch()}
          />
        ) : (
          content.data && (
            <div className="graph-workspace">
              <div className="graph-main">
                {selectedQuery.data && (
                  <div className="selected-summary">
                    <span>
                      <strong>{selectedQuery.data.name}</strong> ·{" "}
                      {selectedQuery.data.type}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => {
                        const panel = document.getElementById("source-panel");
                        panel?.scrollIntoView({
                          behavior: matchMedia("(prefers-reduced-motion: reduce)")
                            .matches
                            ? "instant"
                            : "smooth",
                          block: "start",
                        });
                        panel?.focus({ preventScroll: true });
                      }}
                    >
                      View source <ArrowRight size={14} />
                    </button>
                  </div>
                )}
                {content.data.truncated && (
                  <p className="notice">
                    {content.data.scan_complete
                      ? "Results capped"
                      : "Scan incomplete"}
                    {content.data.scan.files_skipped
                      ? ` — ${content.data.scan.files_skipped} files could not be verified`
                      : ` — ${content.data.completion_reason.replaceAll("_", " ")}`}
                    . Results below may be partial.
                  </p>
                )}
                {!content.data.results.length ? (
                  <Empty title="No matches">
                    {content.data.truncated
                      ? "No hits in the files that could be scanned — coverage was incomplete."
                      : "No indexed file in this snapshot contains that text."}
                  </Empty>
                ) : (
                  <ul className="match-list" aria-label="Content matches">
                    {content.data.results.map((hit, i) => (
                      <li key={i}>
                        <button
                          className={
                            "match-row" +
                            (selected === hit.node_id && around === String(hit.line)
                              ? " active"
                              : "")
                          }
                          onClick={() =>
                            select(hit.node, hit.line, hit.column, hit.end_column)
                          }
                        >
                          <span className="match-location">
                            {hit.path}:{hit.line}:{hit.column}
                          </span>
                          <code>
                            {hit.snippet_start_partial ? "…" : ""}
                            {hit.snippet}
                            {hit.snippet_end_partial ? "…" : ""}
                          </code>
                        </button>
                        <Link
                          className="text-link"
                          to={scoped(
                            base +
                              "?pin=" +
                              hit.node_id +
                              "&line=" +
                              hit.line +
                              "&column=" +
                              hit.column +
                              "&end_column=" +
                              hit.end_column +
                              "&q=" +
                              encodeURIComponent(`What does ${hit.path} do here?`),
                            repo,
                          )}
                        >
                          Ask <ArrowRight size={13} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="small muted canvas-footnote">
                  {content.data.scan.files_scanned} of{" "}
                  {content.data.scan.manifest_entries} indexed files scanned ·{" "}
                  {(content.data.scan.bytes_scanned / 1024).toFixed(0)} KB ·
                  commit {content.data.scope.commit.slice(0, 8)}
                  {content.data.scope.historical ? " · saved snapshot" : ""}
                  {content.data.total !== null
                    ? ` · ${content.data.total} total matches`
                    : ""}
                </p>
              </div>
              {evidencePanel}
            </div>
          )
        )
      ) : query.isPending ? (
        <Loading label="Loading bounded graph…" />
      ) : query.error ? (
        <ErrorNotice error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          {selectedQuery.data && (
            <div className="selected-summary">
              <span>
                <strong>{selectedQuery.data.name}</strong> ·{" "}
                {selectedQuery.data.type}
              </span>
              <button
                className="text-button"
                onClick={() => {
                  const panel = document.getElementById("source-panel");
                  panel?.scrollIntoView({
                    behavior: matchMedia("(prefers-reduced-motion: reduce)")
                      .matches
                      ? "instant"
                      : "smooth",
                    block: "start",
                  });
                  panel?.focus({ preventScroll: true });
                }}
              >
                View source <ArrowRight size={14} />
              </button>
            </div>
          )}
          {relation && graph.edges.length === 0 && (
            <p className="notice subtle">
              No {relation} relationships in the loaded view. Clear the filter
              or expand a matching node.
            </p>
          )}
          <div className="graph-workspace">
            <div className="graph-main">
              {!graph.nodes.length ? (
                <Empty title="No matching nodes">
                  Try a different symbol or node type.
                </Empty>
              ) : (
                <Suspense fallback={<Loading label="Loading graph canvas…" />}>
                  <GraphCanvas
                    graph={graph}
                    onSelect={select}
                    selected={selected}
                  />
                </Suspense>
              )}
              <details className="symbol-list">
                <summary>
                  Browse nodes with keyboard <span>{graph.nodes.length}</span>
                </summary>
                <div>
                  {graph.nodes.map((n) => (
                    <button
                      className={selected === n.id ? "active" : ""}
                      key={n.id}
                      onClick={() => select(n)}
                    >
                      <span className={"node-dot " + n.type} />
                      <span>{n.name}</span>
                      <small>{n.type}</small>
                    </button>
                  ))}
                </div>
              </details>
              <div className="canvas-footnote">
                <span>
                  <Waypoints size={13} />
                  Bounded to 200 nodes · Expand progressively
                </span>
                <span>Typed relationships, inspectable evidence</span>
              </div>
            </div>
            {evidencePanel}
          </div>
        </>
      )}
    </>
  );
}

function Overview({ repo, jobs }: { repo: Repo; jobs: Job[] }) {
  const [confirmation, setConfirmation] = useState("");
  const cache = useQueryClient();
  const navigate = useNavigate();
  const removing = useMutation({
    mutationFn: () =>
      api<Job>(`/repositories/${repo.id}`, {
        method: "DELETE",
        body: JSON.stringify({ confirm_name: confirmation }),
      }),
    onSuccess: () => {
      void cache.invalidateQueries();
      navigate("/workspace");
    },
  });
  const active = jobs.some((j) => ["queued", "running"].includes(j.status));
  return (
    <div className="overview-layout">
      <section>
        <Heading
          title="Repository overview"
          description="The current source snapshot and its verified index."
        />
        <div className="data-grid">
          {[
            ["Files", repo.stats.files],
            ["Functions & tests", repo.stats.functions],
            ["Classes", repo.stats.classes],
            ["Graph relationships", repo.stats.edges],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <span>{String(label)}</span>
              <strong>{number(value)}</strong>
            </div>
          ))}
        </div>
        <h2>Source context</h2>
        <dl className="definition-list">
          <div>
            <dt>Branch</dt>
            <dd>
              <Branch name={repo.branch} />
            </dd>
          </div>
          <div>
            <dt>Indexed commit</dt>
            <dd>
              <code>{repo.commit_sha}</code>
            </dd>
          </div>
          <div>
            <dt>Last indexed</dt>
            <dd>{date(repo.indexed_at)}</dd>
          </div>
          <div>
            <dt>Semantic support</dt>
            <dd>Python static analysis</dd>
          </div>
          <div>
            <dt>Other source files</dt>
            <dd>File references only</dd>
          </div>
        </dl>
        <Link
          className="button primary"
          to={"/repositories/" + repo.id + "/context"}
        >
          Ask with graph context <ArrowRight size={16} />
        </Link>
        {repo.permission === "owner" && !repo.historical && (
          <details className="repository-removal">
            <summary>Remove repository</summary>
            <p>
              This permanently removes this repository from GraphPilot for every
              member, including stored graphs, source snapshots, uploaded input,
              logs and conversations. The original Git repository stays in
              place. Removal cannot be cancelled once confirmed.
            </p>
            {active && (
              <p className="notice">
                Wait for active jobs to finish or cancel them before removal.
              </p>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                removing.mutate();
              }}
            >
              <label htmlFor="remove-repository-name">
                Type {repo.name} to confirm removal
              </label>
              <input
                id="remove-repository-name"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                maxLength={100}
                autoComplete="off"
                required
              />
              {removing.error && <ErrorNotice error={removing.error} />}
              <button
                className="button removal-button"
                disabled={
                  confirmation !== repo.name || active || removing.isPending
                }
              >
                {removing.isPending
                  ? "Requesting removal…"
                  : "Remove repository and stored data"}
              </button>
            </form>
          </details>
        )}
      </section>
      <section>
        <h2>Indexing jobs</h2>
        <Jobs jobs={jobs} repo={repo} />
      </section>
    </div>
  );
}
export function Jobs({ jobs, repo }: { jobs: Job[]; repo?: Repo }) {
  const cache = useQueryClient();
  const cancel = useMutation({
    mutationFn: (id: string) => post("/jobs/" + id + "/cancel"),
    onSuccess: () =>
      void cache.invalidateQueries({ queryKey: ["jobs", repo?.id] }),
  });
  return (
    <>
      {cancel.error && <ErrorNotice error={cancel.error} />}
      <div className="job-list">
        {jobs.map((j) => (
          <div className="job-row" key={j.id}>
            <div>
              <strong>
                {j.kind === "index"
                  ? "Source index"
                  : j.kind === "delete"
                    ? "Repository removal"
                    : "GitHub synchronization"}
              </strong>
              <Status status={j.status} />
            </div>
            <p>{j.message}</p>
            <small>
              {date(j.created_at)} · attempt {j.attempts}
            </small>
            {["queued", "running"].includes(j.status) &&
              j.kind !== "delete" && (
                <button
                  className="text-button"
                  disabled={
                    repo?.permission === "read" ||
                    cancel.isPending ||
                    j.cancel_requested
                  }
                  onClick={() => cancel.mutate(j.id)}
                >
                  {j.cancel_requested ? "Cancellation requested" : "Cancel job"}
                </button>
              )}
          </div>
        ))}
      </div>
    </>
  );
}
function Timeline({
  repo,
  sync,
  busy,
}: {
  repo: Repo;
  sync: () => void;
  busy: boolean;
}) {
  const read = <T,>(path: string) => api<T>(scoped(path, repo));
  const [kind, setKind] = useState("");
  const query = useQuery({
    queryKey: [
      "history",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      repo.sync_state.last_synced_at,
      kind,
    ],
    queryFn: () =>
      read<{ items: Node[]; coverage: string; sync: Record<string, unknown> }>(
        "/repositories/" + repo.id + "/history?kind=" + kind,
      ),
  });
  return (
    <>
      <Heading
        title="The context behind the code."
        description="Commits, issues, pull requests and workflow runs connected by source evidence."
        action={
          repo.source_type === "github" ? (
            <button className="button secondary" disabled={busy} onClick={sync}>
              <RefreshCw size={15} />
              Sync GitHub history
            </button>
          ) : undefined
        }
      />
      <div className="filter-row">
        <label>
          Show
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All history</option>
            {[
              "Commit",
              "Issue",
              "PullRequest",
              "WorkflowRun",
              "LogArtifact",
              "Decision",
            ].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorNotice error={query.error} />
      ) : !query.data?.items.length ? (
        <Empty title="No historical evidence synchronized yet">
          {repo.source_type === "github"
            ? "Sync GitHub history to retrieve available commits, issues, pull requests and workflow metadata."
            : "GitHub history synchronization is available for connected GitHub repositories."}
        </Empty>
      ) : (
        <div className="timeline">
          {query.data.items.map((n) => (
            <article key={n.id}>
              <span className="timeline-icon">
                {n.type === "Commit" ? (
                  <GitCommitHorizontal size={17} />
                ) : n.type === "PullRequest" ? (
                  <GitPullRequest size={17} />
                ) : (
                  <History size={17} />
                )}
              </span>
              <div>
                <div className="timeline-meta">
                  <span>{n.type}</span>
                  <time>{date(n.timestamp)}</time>
                  {n.status && <Status status={n.status} />}
                </div>
                <h2>
                  <Link
                    to={scoped(
                      "/repositories/" + repo.id + "?node=" + n.id,
                      repo,
                    )}
                  >
                    {n.name}
                  </Link>
                </h2>
                <p>{(n.summary || n.body || "").slice(0, 300)}</p>
                {safeUrl(n.url) && (
                  <a
                    className="text-link"
                    href={safeUrl(n.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View on GitHub <ExternalLink size={13} />
                  </a>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="notice subtle">
        References are links, not proof of a fix. Selected failed-job logs are
        archived when GitHub permits access. Automated redaction may miss
        unknown secret formats. Expired or deleted logs cannot be recovered
        here.
      </p>
      {Array.isArray(repo.sync_state.warnings) &&
        repo.sync_state.warnings.map((w, i) => (
          <p className="notice" key={i}>
            {String(w)}
          </p>
        ))}
    </>
  );
}
function Impact({ repo }: { repo: Repo }) {
  const read = <T,>(path: string) => api<T>(scoped(path, repo));
  const [params] = useSearchParams();
  const [selected, setSelected] = useState(params.get("node") || "");
  const [term, setTerm] = useState("");
  const [depth, setDepth] = useState("2");
  const query = useQuery({
    queryKey: ["impact-search", repo.id, repo.branch, repo.snapshot_id, term],
    queryFn: () =>
      read<{ results: Node[] }>(
        "/repositories/" + repo.id + "/search?q=" + encodeURIComponent(term),
      ),
    enabled: term.length > 1,
  });
  const result = useQuery({
    queryKey: [
      "impact",
      repo.id,
      repo.branch,
      repo.snapshot_id,
      selected,
      depth,
    ],
    queryFn: () =>
      read<ImpactResult>(
        "/repositories/" + repo.id + "/impact/" + selected + "?depth=" + depth,
      ),
    enabled: !!selected,
  });
  return (
    <>
      <Heading
        title="See what a change could touch."
        description="Trace inbound static dependencies. Indirect impact is a possibility to investigate."
      />
      <div className="impact-controls">
        <label>
          Find a file or function
          <input
            value={term}
            placeholder="Search a known symbol…"
            onChange={(e) => setTerm(e.target.value)}
          />
        </label>
        <label>
          Relationship depth
          <select value={depth} onChange={(e) => setDepth(e.target.value)}>
            {[1, 2, 3].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
      </div>
      {query.error && <ErrorNotice error={query.error} />}
      <div className="impact-options">
        {query.data?.results.map((n) => (
          <button
            className={
              "button secondary " + (n.id === selected ? "selected" : "")
            }
            onClick={() => setSelected(n.id)}
            key={n.id}
          >
            {n.name}
            <small>{n.path}</small>
          </button>
        ))}
      </div>
      {!selected ? (
        <Empty title="Choose a starting point">
          Select a source entity to inspect its callers and dependent files.
        </Empty>
      ) : result.isPending ? (
        <Loading />
      ) : result.error ? (
        <ErrorNotice error={result.error} />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Potentially affected entity</th>
                  <th>Distance</th>
                  <th>Evidence classification</th>
                </tr>
              </thead>
              <tbody>
                {result.data?.results.map((r) => (
                  <tr key={r.node.id}>
                    <td>
                      <Link
                        to={scoped(
                          "/repositories/" + repo.id + "?node=" + r.node.id,
                          repo,
                        )}
                      >
                        {r.node.name}
                      </Link>
                      <small>{r.node.path}</small>
                    </td>
                    <td>{r.distance}</td>
                    <td>{r.classification}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.data?.has_more && (
            <p className="notice">
              {result.data.total != null
                ? `Showing ${result.data.returned ?? result.data.results.length} of ${result.data.total} inbound dependents within depth ${result.data.max_depth ?? depth}.`
                : "Traversal stopped at a work limit before every caller layer completed, so more dependents may exist than shown."}
            </p>
          )}
          {!result.data?.results.length && (
            <p className="notice">
              No inbound dependencies were found within this depth. This does
              not prove a change is safe.
            </p>
          )}
          <p className="notice subtle">{result.data?.unknown}</p>
        </>
      )}
    </>
  );
}
function Diagnostics({ repo, jobs }: { repo: Repo; jobs: Job[] }) {
  return (
    <>
      <Heading
        title="Know what the index knows."
        description="Observed indexing results and explicit gaps in graph coverage."
      />
      <div className="diagnostics-grid">
        <section>
          <h2>Latest index checks</h2>
          <dl className="definition-list">
            {[
              ["Resolved static calls", repo.stats.resolved_calls],
              ["Unresolved calls", repo.stats.unresolved_calls],
              ["Files parsed in last scan", repo.stats.parsed_files],
              ["Unchanged files skipped", repo.stats.skipped_files],
              ["Deleted files", repo.stats.deleted_files],
              ["Graph writes in last scan", repo.stats.graph_writes],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt>{String(label)}</dt>
                <dd>{number(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="notice subtle">
            Successful publication validates node and relationship counts. This
            is an indexing integrity check; security certification and runtime
            tests are not implied.
          </p>
          <h2>Parser observations</h2>
          {Array.isArray(repo.stats.parse_errors) &&
          repo.stats.parse_errors.length ? (
            repo.stats.parse_errors.map((e, i) => (
              <p className="notice" key={i}>
                {(e as { path: string; message: string }).path}:{" "}
                {(e as { message: string }).message}
              </p>
            ))
          ) : (
            <p className="muted">
              No parser errors were recorded in this snapshot.
            </p>
          )}
          <h2>Test results</h2>
          <p className="muted">
            Repository code is never executed during indexing. Connected test
            results can appear in synchronized workflow metadata.
          </p>
        </section>
        <section>
          <h2>Ingestion jobs</h2>
          <Jobs repo={repo} jobs={jobs} />
        </section>
      </div>
    </>
  );
}
