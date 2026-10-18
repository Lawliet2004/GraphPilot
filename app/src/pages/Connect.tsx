import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  FolderGit2,
  GitFork,
  Upload,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api, post, type Capabilities, type Repo } from "../lib/api";
import { ErrorNotice, Heading } from "../components/ui";
import { GitHubConnection } from "../components/GitHubConnection";
export function Connect() {
  const [type, setType] = useState<"github" | "local" | "archive">("github");
  const [source, setSource] = useState("");
  const [branch, setBranch] = useState("main");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const caps = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Capabilities>("/capabilities"),
  });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      let result: { repository: Repo };
      if (type === "archive") {
        if (!file) throw new Error("Choose a ZIP archive first.");
        const body = new FormData();
        body.set("file", file);
        body.set("branch", branch);
        result = await api("/repositories/upload", { method: "POST", body });
      } else
        result = await post("/repositories", {
          source_type: type,
          source,
          branch,
        });
      await cache.invalidateQueries({ queryKey: ["repositories"] });
      navigate(`/repositories/${result.repository.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page connect-page">
      <Link className="back-link" to="/workspace">
        <ArrowLeft size={15} />
        Repositories
      </Link>
      <Heading
        title="Add a repository."
        description="Connect a source. We’ll map the files, symbols and relationships."
      />
      <div className="connect-layout">
        <section className="form-panel">
          <GitHubConnection />
          <div
            className="source-tabs"
            role="group"
            aria-label="Repository source"
          >
            {(["github", "archive", "local"] as const).map((t) => (
              <button
                key={t}
                aria-pressed={type === t}
                onClick={() => {
                  setType(t);
                  setError(undefined);
                }}
                disabled={t === "local" && !caps.data?.local_sources}
              >
                {t === "github" ? (
                  <GitFork size={18} />
                ) : t === "archive" ? (
                  <Upload size={18} />
                ) : (
                  <FolderGit2 size={18} />
                )}
                {
                  {
                    github: "GitHub",
                    archive: "ZIP upload",
                    local: "Server-local",
                  }[t]
                }
              </button>
            ))}
          </div>
          {error !== undefined && <ErrorNotice error={error} />}
          <form onSubmit={submit}>
            {type === "github" ? (
              <label>
                Public GitHub repository URL
                <input
                  type="url"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  required
                />
                <small>
                  Public repositories only. Private access requires a configured
                  integration.
                </small>
              </label>
            ) : type === "local" ? (
              <label>
                Server-local Git repository path
                <input
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  required
                />
                <small>
                  This path must be within an administrator-configured allowed
                  directory on the server.
                </small>
              </label>
            ) : (
              <label className="upload-field">
                <Upload size={29} />
                <strong>Choose your source archive</strong>
                <span>ZIP · up to 25 MB compressed, 100 MB extracted</span>
                <input
                  aria-label="Source ZIP archive"
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  required
                />
                {file && <span>{file.name}</span>}
              </label>
            )}
            <label>
              {type === "archive" ? "Snapshot branch label" : "Branch"}
              <input
                aria-label={
                  type === "archive" ? "Snapshot branch label" : "Branch"
                }
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="main"
                required
                maxLength={200}
              />
              <small>
                {type === "archive"
                  ? "Label this source snapshot."
                  : "Use the exact branch name from your repository."}
              </small>
            </label>
            <div className="form-actions">
              <Link className="button secondary" to="/workspace">
                Cancel
              </Link>
              <button className="button primary" disabled={busy}>
                {busy ? "Connecting…" : "Connect & index"}
                <ArrowRight size={16} />
              </button>
            </div>
          </form>
        </section>
        <aside className="connect-explainer">
          <h2>A map of what’s there.</h2>
          <ol>
            <li>
              <strong>Read the source</strong>
              <p>Files are read as data. Indexing does not run your code.</p>
            </li>
            <li>
              <strong>Build the connections</strong>
              <p>
                Python functions, classes, imports and static calls become a
                FalkorDB graph.
              </p>
            </li>
            <li>
              <strong>Follow the evidence</strong>
              <p>
                Search, explore dependencies and inspect exact source regions.
              </p>
            </li>
          </ol>
          <p className="notice subtle">
            Other languages get file references. Dynamic calls remain
            unverified. No model or paid API is required.
          </p>
          {!caps.data?.local_sources && (
            <p className="small muted">
              Server-local access is disabled. For a repository on your
              computer, upload a ZIP or connect its public GitHub URL.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
