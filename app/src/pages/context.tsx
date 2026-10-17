import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  MessageSquare,
  Search,
  Send,
  Waypoints,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  date,
  post,
  scoped,
  type ContextResult,
  type Conversation,
  type Repo,
} from "../lib/api";
import { Empty, ErrorNotice, Loading } from "../components/ui";
export function ContextExplorer({ repo }: { repo: Repo }) {
  const [question, setQuestion] = useState("");
  const cache = useQueryClient();
  const base = "/repositories/" + repo.id;
  const history = useQuery({
    queryKey: ["conversations", repo.id, repo.branch, repo.snapshot_id],
    queryFn: () => api<Conversation[]>(scoped(base + "/conversations", repo)),
  });
  const mutation = useMutation({
    mutationFn: (text: string) =>
      post<ContextResult>(scoped(base + "/context", repo), { question: text }),
    onSuccess: () => {
      setQuestion("");
      void cache.invalidateQueries({
        queryKey: ["conversations", repo.id, repo.branch, repo.snapshot_id],
      });
    },
  });
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (question.trim()) mutation.mutate(question.trim());
  }
  return (
    <div className="context-layout">
      <section className="conversation">
        <div className="context-heading">
          <MessageSquare size={22} />
          <div>
            <h2>Ask a better-informed question.</h2>
            <p>
              Search this repository’s graph. Inspect the evidence behind each
              result.
            </p>
          </div>
        </div>
        {history.isPending ? (
          <Loading label="Loading conversations…" />
        ) : history.error ? (
          <ErrorNotice error={history.error} />
        ) : !history.data?.length ? (
          <Empty title="Start with something specific.">
            Try a function name, file path, dependency question or synchronized
            issue number.
          </Empty>
        ) : (
          <div className="conversation-list">
            {[...history.data].reverse().map((c) => (
              <article key={c.id}>
                <div className="user-question">
                  <strong>{c.question}</strong>
                  <time>{date(c.created_at)}</time>
                </div>
                <ContextAnswer result={c.response} repo={repo} />
              </article>
            ))}
          </div>
        )}
        {mutation.isPending && (
          <Loading label="Retrieving graph evidence and checking context…" />
        )}
        {mutation.error && <ErrorNotice error={mutation.error} />}
        <form className="question-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="question">
            Ask about this repository
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Which functions call this symbol?"
            rows={2}
            minLength={2}
            maxLength={2000}
            required
          />
          <div>
            <span>
              Scoped to <strong>{repo.name}</strong> / {repo.branch}
            </span>
            <button
              className="button primary"
              disabled={mutation.isPending || question.trim().length < 2}
            >
              <Send size={15} />
              Ask GraphPilot
            </button>
          </div>
        </form>
      </section>
      <aside className="context-guide">
        <Waypoints size={28} strokeWidth={1.3} />
        <h2>Context you can inspect.</h2>
        <ol>
          <li>
            <strong>Find a foothold</strong>
            <p>
              Exact symbols and file names give retrieval a clear starting
              point.
            </p>
          </li>
          <li>
            <strong>Follow relationships</strong>
            <p>
              Direct neighbors add code and historical context within a bounded
              search.
            </p>
          </li>
          <li>
            <strong>Check the source</strong>
            <p>
              Open cited regions and distinguish observed evidence from unknown
              behavior.
            </p>
          </li>
        </ol>
        <p className="notice subtle">
          Graph search works without a model. When configured, AI synthesis uses
          retrieved evidence and must cite it.
        </p>
      </aside>
    </div>
  );
}
function ContextAnswer({
  result,
  repo,
}: {
  result: ContextResult;
  repo: Repo;
}) {
  const names = new Map(result.results.map((n) => [n.id, n.name]));
  return (
    <div className="context-answer">
      <div className="answer-label">
        <Search size={15} />
        {result.mode === "ai" ? "Evidence-based synthesis" : "Graph retrieval"}
      </div>
      {result.answer && <p className="model-answer">{result.answer}</p>}
      <p className="notice subtle">{result.notice}</p>
      {result.results.length > 0 && (
        <>
          <h3>Matching evidence</h3>
          <div className="context-results">
            {result.results.slice(0, 8).map((n) => (
              <Link
                key={n.id}
                to={scoped("/repositories/" + repo.id + "?node=" + n.id, {
                  branch: result.branch || repo.branch,
                  snapshot_id: result.snapshot_id,
                })}
              >
                <span className={"node-dot " + n.type} />
                <div>
                  <strong>{n.name}</strong>
                  <small>
                    {n.path || n.type}
                    {n.line ? ":" + n.line : ""} · {n.score_meaning}
                  </small>
                </div>
                <ArrowUpRight size={15} />
              </Link>
            ))}
          </div>
        </>
      )}
      {result.relationships.length > 0 && (
        <details className="relationship-details">
          <summary>
            Relationships followed ({result.relationships.length})
          </summary>
          {result.relationships.map((e) => (
            <p key={e.id}>
              <code>{names.get(e.source)}</code>
              <span>{e.type}</span>
              <code>{names.get(e.target)}</code>
            </p>
          ))}
        </details>
      )}
      {result.evidence.length > 0 && (
        <div className="citations">
          {result.evidence.map((e) => (
            <Link
              key={e.citation}
              to={scoped("/repositories/" + repo.id + "?node=" + e.entity_id, {
                branch: result.branch || repo.branch,
                snapshot_id: result.snapshot_id,
              })}
            >
              [{e.citation}] {e.path || e.name}
              {e.start_line ? ":" + e.start_line : ""}
              <ArrowRight size={12} />
            </Link>
          ))}
        </div>
      )}
      <details className="retrieval-diagnostics">
        <summary>Retrieval diagnostics</summary>
        <p>
          {result.diagnostics.latency_ms} ms ·{" "}
          {result.diagnostics.graph_queries} graph queries ·{" "}
          {result.diagnostics.returned_nodes} entities
        </p>
        <p>{result.diagnostics.ranking}</p>
        {result.warnings.map((w, i) => (
          <p key={i}>{w}</p>
        ))}
      </details>
    </div>
  );
}
