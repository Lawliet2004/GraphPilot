import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  MessageSquare,
  Search,
  Send,
} from "lucide-react";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  date,
  post,
  scoped,
  type ContextResult,
  type Conversation,
  type Repo,
  type ModelCredentialStatus,
} from "../lib/api";
import { ErrorNotice, Loading } from "../components/ui";
export function ContextExplorer({ repo }: { repo: Repo }) {
  const [params, setParams] = useSearchParams();
  const [question, setQuestion] = useState(params.get("q") || "");
  const input = useRef<HTMLTextAreaElement>(null);
  const cache = useQueryClient();
  const base = "/repositories/" + repo.id;
  // A content-search hit can pin an exact source range onto this question.
  const pin = params.get("pin");
  const pinLine = params.get("line");
  const pinned = pin
    ? {
        node_id: pin,
        around: pinLine ? Number(pinLine) : undefined,
        start: params.get("start") ? Number(params.get("start")) : undefined,
        end: params.get("end") ? Number(params.get("end")) : undefined,
        column: params.get("column") ? Number(params.get("column")) : undefined,
        end_column: params.get("end_column")
          ? Number(params.get("end_column"))
          : undefined,
      }
    : undefined;
  const model = useQuery({
    queryKey: ["model-credential"],
    queryFn: () => api<ModelCredentialStatus>("/model"),
  });
  const history = useQuery({
    queryKey: ["conversations", repo.id, repo.branch, repo.snapshot_id],
    queryFn: () => api<Conversation[]>(scoped(base + "/conversations", repo)),
  });
  const mutation = useMutation({
    mutationFn: (text: string) =>
      post<ContextResult>(scoped(base + "/context", repo), {
        question: text,
        source: pinned,
      }),
    onSuccess: () => {
      setQuestion("");
      clearPin();
      void cache.invalidateQueries({
        queryKey: ["conversations", repo.id, repo.branch, repo.snapshot_id],
      });
    },
  });
  function clearPin() {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const key of [
        "pin",
        "line",
        "start",
        "end",
        "column",
        "end_column",
        "q",
      ])
        next.delete(key);
      return next;
    });
  }
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
            <h2>Ask about your code.</h2>
            <p>
              Understand the app, investigate a bug, or explore an improvement.
            </p>
          </div>
        </div>
        <form className="question-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="question">
            Ask about this repository
          </label>
          <textarea
            id="question"
            ref={input}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What could make this app easier to use?"
            rows={3}
            minLength={2}
            maxLength={2000}
            required
          />
          <div>
            <span>
              {model.data?.configured ? (
                `${model.data.model} · ${repo.branch}`
              ) : (
                <Link to="/settings">Add a model key for AI answers</Link>
              )}
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
        <p className="context-scope">
          Relevant source is gathered automatically. With a model key, selected
          excerpts go to your provider when you ask.
        </p>
        {pinned && (
          <p className="notice subtle pinned-source">
            Source pinned{pinLine ? ` · line ${pinLine}` : ""} on this snapshot.
            <button className="text-button" type="button" onClick={clearPin}>
              Remove
            </button>
          </p>
        )}
        {!history.data?.length && !history.isPending && !history.error && (
          <div className="question-starters" aria-label="Suggested questions">
            {[
              "Explain how this app works",
              "Suggest a feature to improve the user experience",
              "Where should I start debugging this app?",
            ].map((text) => (
              <button
                className="button secondary"
                key={text}
                onClick={() => {
                  setQuestion(text);
                  input.current?.focus();
                }}
              >
                {text}
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
        )}
        {mutation.isPending && (
          <Loading label="Reading relevant source and preparing an answer…" />
        )}
        {mutation.error && <ErrorNotice error={mutation.error} />}
        {history.isPending ? (
          <Loading label="Loading conversations…" />
        ) : history.error ? (
          <ErrorNotice error={history.error} />
        ) : (
          <div className="conversation-list">
            {history.data?.map((c) => (
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
      </section>
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
          <details className="answer-sources" open={!result.answer}>
            <summary>
              Source files & matches ({Math.min(result.results.length, 8)})
            </summary>
            <div className="context-results">
              {result.results.slice(0, 8).map((n) => (
                <Link
                  key={n.id}
                  to={scoped(
                    "/repositories/" + repo.id + "/code?node=" + n.id,
                    {
                      branch: result.branch || repo.branch,
                      snapshot_id: result.snapshot_id,
                    },
                  )}
                >
                  <span className={"node-dot " + n.type} />
                  <div>
                    <strong>{n.name}</strong>
                    <small>
                      {n.path || n.type}
                      {n.line ? ":" + n.line : ""}
                    </small>
                  </div>
                  <ArrowUpRight size={15} />
                </Link>
              ))}
            </div>
          </details>
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
          {result.evidence.map((e) => {
            const range = e.match
              ? `:${e.match.line}:${e.match.column}`
              : e.start_line == null
                ? ""
                : e.end_line != null && e.end_line > e.start_line
                  ? `:${e.start_line}–${e.end_line}${e.end_line_partial ? "…" : ""}`
                  : `:${e.start_line}${e.end_line_partial ? "…" : ""}`;
            return (
              <Link
                key={e.citation}
                to={scoped(
                  "/repositories/" +
                    repo.id +
                    "/code?node=" +
                    e.entity_id +
                    (e.match
                      ? "&around=" +
                        e.match.line +
                        "&column=" +
                        e.match.column +
                        "&end_column=" +
                        e.match.end_column
                      : ""),
                  {
                    branch: result.branch || repo.branch,
                    snapshot_id: result.snapshot_id,
                  },
                )}
              >
                [{e.citation}] {e.path || e.name}
                {range}
                {e.pinned ? " · pinned" : ""}
                {e.line_excerpt?.partial ? " · partial line" : ""}
                {e.truncated ? " · excerpt" : ""}
                <ArrowRight size={12} />
              </Link>
            );
          })}
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
