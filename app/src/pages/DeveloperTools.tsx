import { useQuery } from "@tanstack/react-query";
import {
  Check,
  Cloud,
  Copy,
  FolderGit2,
  GitBranch,
  Info,
  LoaderCircle,
  MessageSquare,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  ConnectLink,
  Empty,
  ErrorNotice,
  Heading,
  Loading,
} from "../components/ui";

const CLI = "./scripts/graphpilot";
const SERVICES = ["api", "worker", "web", "postgres", "falkordb"] as const;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PROFILE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$/;
const CODESPACE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const WORKSPACE = /^\/[A-Za-z0-9_./-]{1,199}$/;

/** Single-quote shell quoting; embedded ' becomes '\'' */
function q(value: string) {
  return "'" + value.replaceAll("'", "'\\''") + "'";
}
function flag(name: string, value: string) {
  const v = value.trim();
  return v ? ` ${name} ${q(v)}` : "";
}
/** Nonempty invalid input blocks the command and names the fix. */
function invalid(value: string, test: RegExp) {
  return value.trim() !== "" && !test.test(value.trim());
}
function FieldError({ show, text }: { show: boolean; text: string }) {
  return show ? <small className="field-error">{text}</small> : null;
}

function CommandBlock({
  command,
  placeholder,
}: {
  command: string | null;
  placeholder: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  async function copy() {
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      setState("copied");
    } catch {
      let ok = false;
      try {
        const el = document.createElement("textarea");
        el.value = command;
        el.style.position = "fixed";
        el.style.opacity = "0";
        document.body.appendChild(el);
        el.select();
        ok = document.execCommand("copy");
        el.remove();
      } catch {
        ok = false;
      }
      setState(ok ? "copied" : "failed");
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2400);
  }
  return (
    <div className="command-block">
      <code className={command ? undefined : "command-pending"}>
        {command ?? placeholder}
      </code>
      <div className="command-actions">
        <button
          className="button secondary small-button"
          disabled={!command}
          onClick={() => void copy()}
        >
          {state === "copied" ? <Check size={14} /> : <Copy size={14} />}
          {state === "copied" ? "Copied" : "Copy"}
        </button>
        {state === "failed" && (
          <span className="command-copy-error" role="status">
            Copy failed — select the command text manually.
          </span>
        )}
      </div>
    </div>
  );
}

function ToolGroup({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="tool-group">
      <div className="tool-group-head">
        <Icon size={19} />
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function BackendStatus() {
  const { user } = useAuth();
  const health = useQuery({
    queryKey: ["backend-health"],
    queryFn: () =>
      api<{ status: string; checks: Record<string, string> }>("/health/ready"),
    refetchInterval: 30000,
    retry: 0,
  });
  const tokens = useQuery({
    queryKey: ["cli-credentials", user?.id],
    queryFn: () =>
      api<{ id: string; revoked: boolean; expires_at: string }[]>(
        "/cli/tokens",
      ),
    retry: 0,
  });
  const now = Date.now();
  const active = tokens.data?.filter(
    (t) => !t.revoked && Date.parse(t.expires_at) > now,
  ).length;
  return (
    <div className="tools-status" role="group" aria-label="Service status">
      <div className="tools-status-item">
        <span className="tools-status-label">Backend API</span>
        {health.isPending ? (
          <span className="tools-status-detail">
            <LoaderCircle className="spin" size={13} /> Checking…
          </span>
        ) : health.error ? (
          <>
            <span className="status status-failed">
              <span />
              Unreachable
            </span>
            <span className="tools-status-detail">{health.error.message}</span>
          </>
        ) : health.data.status === "ready" ? (
          <>
            <span className="status status-ready">
              <span />
              Ready
            </span>
            <span className="tools-status-detail">
              {Object.entries(health.data.checks)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}
            </span>
          </>
        ) : (
          <>
            <span className="status status-pending">
              <span />
              Degraded
            </span>
            <span className="tools-status-detail">
              {Object.entries(health.data.checks)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}
            </span>
          </>
        )}
      </div>
      <div className="tools-status-item">
        <span className="tools-status-label">CLI access</span>
        {tokens.isPending ? (
          <span className="tools-status-detail">
            <LoaderCircle className="spin" size={13} /> Checking…
          </span>
        ) : tokens.error ? (
          <span className="tools-status-detail">
            Credential status unavailable.{" "}
            <button
              className="text-button"
              onClick={() => void tokens.refetch()}
            >
              Try again
            </button>
          </span>
        ) : (
          <>
            <span className="tools-status-detail">
              <strong>
                {active === 0
                  ? "No active CLI credentials"
                  : `${active} active CLI credential${active === 1 ? "" : "s"}`}
              </strong>
            </span>
            <Link className="text-link" to="/settings">
              Manage in Settings
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

function CodeQuestions({ repos }: { repos: Repo[] }) {
  const [task, setTask] = useState("ask");
  const [repoId, setRepoId] = useState("");
  const [question, setQuestion] = useState("");
  const [branch, setBranch] = useState("");
  const [revision, setRevision] = useState("");
  const [jobId, setJobId] = useState("");
  const repo = repos.find((r) => r.id === (repoId || repos[0]?.id)) ?? null;
  const questionError =
    question.trim().length > 0 && question.trim().length < 2
      ? "Questions need at least 2 characters."
      : "";
  const revisionError = invalid(revision, UUID)
    ? "Use a lowercase UUID — copy the snapshot id from the repository page."
    : "";
  const jobError = invalid(jobId, UUID)
    ? "Use a lowercase UUID from jobs list output."
    : "";
  const command = (() => {
    if (task === "ask") {
      if (!repo || question.trim().length < 2 || questionError || revisionError)
        return null;
      return `${CLI} ask ${q(repo.id)} ${q(question.trim())}${flag("--branch", branch)}${flag("--revision", revision)}`;
    }
    if (task === "jobs") return repo ? `${CLI} jobs list ${q(repo.id)}` : null;
    return jobId.trim() && !jobError
      ? `${CLI} jobs cancel ${q(jobId.trim())}`
      : null;
  })();
  if (!repos.length) {
    return (
      <ToolGroup
        icon={MessageSquare}
        title="Code questions"
        description="Ask about a repository or manage its indexing jobs."
      >
        <Empty title="Connect a repository first." action={<ConnectLink />}>
          Repository questions and job commands need a connected source.
        </Empty>
      </ToolGroup>
    );
  }
  return (
    <ToolGroup
      icon={MessageSquare}
      title="Code questions"
      description="Ask about a repository or manage its indexing jobs."
    >
      <div className="tool-fields">
        <label>
          Task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            <option value="ask">Ask a question</option>
            <option value="jobs">List repository jobs</option>
            <option value="cancel">Cancel a job</option>
          </select>
        </label>
        {task !== "cancel" && (
          <label>
            Repository
            <select
              value={repo?.id ?? ""}
              onChange={(e) => setRepoId(e.target.value)}
            >
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} — {r.branch}
                </option>
              ))}
            </select>
          </label>
        )}
        {task === "ask" && (
          <>
            <label>
              Question
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Which functions call the payment handler?"
                maxLength={2000}
                aria-invalid={!!questionError}
              />
              <FieldError show={!!questionError} text={questionError} />
            </label>
            <details className="tool-advanced">
              <summary>Advanced options</summary>
              <div className="tool-row">
                <label>
                  Branch <small>optional</small>
                  <input
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder={repo?.branch || "main"}
                  />
                </label>
                <label>
                  Saved revision <small>optional</small>
                  <input
                    value={revision}
                    onChange={(e) => setRevision(e.target.value)}
                    placeholder="Snapshot UUID"
                    aria-invalid={!!revisionError}
                  />
                  <FieldError show={!!revisionError} text={revisionError} />
                </label>
              </div>
            </details>
          </>
        )}
        {task === "cancel" && (
          <label>
            Job ID
            <input
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="UUID from jobs list output"
              aria-invalid={!!jobError}
            />
            <FieldError show={!!jobError} text={jobError} />
          </label>
        )}
      </div>
      <CommandBlock
        command={command}
        placeholder={
          task === "cancel"
            ? "Enter the job ID to build the command."
            : "Choose a repository and enter a question to build the command."
        }
      />
    </ToolGroup>
  );
}

function CloudRunner() {
  const [task, setTask] = useState("status");
  const [profile, setProfile] = useState("");
  const [codespace, setCodespace] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [service, setService] = useState<string>(SERVICES[0]);
  const [lines, setLines] = useState("200");
  const named = profile.trim();
  const profileError = invalid(profile, PROFILE)
    ? "Profile names are 1–63 chars: letters, numbers, _ . - (start with a letter or number)."
    : "";
  const codespaceError = invalid(codespace, CODESPACE)
    ? "Codespace names are 1–63 lowercase letters, numbers or hyphens — no leading or trailing hyphen."
    : "";
  const workspaceParts = workspace.trim().split("/").slice(1);
  const workspaceError =
    invalid(workspace, WORKSPACE) ||
    (workspace.trim() !== "" &&
      workspaceParts.some((part) => !part || part === "." || part === ".."))
      ? "Use a normalized absolute path like /workspaces/my-project — no trailing slash or '.' segments."
      : "";
  const command = (() => {
    if (profileError || codespaceError || workspaceError) return null;
    if (task === "configure") {
      if (!named || !codespace.trim()) return null;
      return `${CLI} runner configure ${q(named)} --codespace ${q(codespace.trim())}${flag("--workspace", workspace)}`;
    }
    if (task === "list") return `${CLI} runner list`;
    if (task === "logs") {
      const n = Math.max(1, Math.min(5000, parseInt(lines) || 200));
      return `${CLI} runner logs${named ? " " + q(named) : ""} --service ${q(service)} --lines ${n}`;
    }
    return `${CLI} runner ${task}${named ? " " + q(named) : ""}`;
  })();
  return (
    <ToolGroup
      icon={Cloud}
      title="Cloud Runner"
      description="Drive your existing GitHub Codespace through the CLI."
    >
      <p className="tool-note">
        <Info size={13} />
        <span>
          These commands use the GitHub CLI (<code>gh auth login</code>) with
          your GitHub account to control your Codespace. Your website sign-in is
          separate — this page grants no cloud access.
        </span>
      </p>
      <div className="tool-fields">
        <label>
          Task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            <option value="status">Runner status</option>
            <option value="configure">Configure a profile</option>
            <option value="list">List profiles</option>
            <option value="start">Start Codespace</option>
            <option value="stop">Stop Codespace</option>
            <option value="check">Run health check</option>
            <option value="logs">Read service logs</option>
            <option value="ssh">Open an SSH session</option>
          </select>
        </label>
        <label>
          Profile {task === "configure" ? "" : <small>optional</small>}
          <input
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            placeholder="default"
            aria-invalid={!!profileError}
          />
          <FieldError show={!!profileError} text={profileError} />
        </label>
        {task === "configure" && (
          <>
            <label>
              Codespace name
              <input
                value={codespace}
                onChange={(e) => setCodespace(e.target.value)}
                placeholder="From gh codespace list"
                aria-invalid={!!codespaceError}
              />
              <FieldError show={!!codespaceError} text={codespaceError} />
            </label>
            <label>
              Workspace path <small>optional</small>
              <input
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
                placeholder="/workspaces/GraphPilot"
                aria-invalid={!!workspaceError}
              />
              <FieldError show={!!workspaceError} text={workspaceError} />
            </label>
          </>
        )}
        {task === "logs" && (
          <div className="tool-row">
            <label>
              Service
              <select
                value={service}
                onChange={(e) => setService(e.target.value)}
              >
                {SERVICES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Lines
              <input
                type="number"
                min={1}
                max={5000}
                value={lines}
                onChange={(e) => setLines(e.target.value)}
              />
            </label>
          </div>
        )}
      </div>
      <CommandBlock
        command={command}
        placeholder="Enter a profile and Codespace name to build the command."
      />
    </ToolGroup>
  );
}

function DailyGit() {
  const [task, setTask] = useState("daily");
  const [path, setPath] = useState(".");
  const [branch, setBranch] = useState("");
  const [create, setCreate] = useState(false);
  const [files, setFiles] = useState("");
  const [message, setMessage] = useState("");
  const command = (() => {
    if (!path.trim()) return null;
    const p = ` --path ${q(path.trim())}`;
    if (task === "switch") {
      if (!branch.trim()) return null;
      return `${CLI} git switch ${q(branch.trim())}${create ? " --create" : ""}${p}`;
    }
    if (task === "stage") {
      const list = files
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
      if (!list.length) return null;
      return `${CLI} git stage ${list.map(q).join(" ")}${p}`;
    }
    if (task === "commit") {
      if (!message.trim()) return null;
      return `${CLI} git commit --message ${q(message.trim())}${p}`;
    }
    return `${CLI} git ${task}${p}`;
  })();
  return (
    <ToolGroup
      icon={GitBranch}
      title="Daily Git"
      description="Everyday Git flow for any checkout on your machine."
    >
      <div className="tool-fields">
        <label>
          Task
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            <option value="daily">Daily overview</option>
            <option value="status">Status</option>
            <option value="diff">Diff</option>
            <option value="log">Log</option>
            <option value="switch">Switch branch</option>
            <option value="stage">Stage files</option>
            <option value="commit">Commit</option>
            <option value="pull">Pull</option>
            <option value="push">Push</option>
          </select>
        </label>
        <label>
          Repository path
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="."
          />
          <small>A Git checkout on the machine running the CLI.</small>
        </label>
        {task === "switch" && (
          <>
            <label>
              Branch
              <input
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                placeholder="feature/graph-inspector"
              />
            </label>
            <label className="tool-check">
              <input
                type="checkbox"
                checked={create}
                onChange={(e) => setCreate(e.target.checked)}
              />
              <span>Create the branch if it does not exist</span>
            </label>
          </>
        )}
        {task === "stage" && (
          <label>
            Files
            <textarea
              rows={3}
              value={files}
              onChange={(e) => setFiles(e.target.value)}
              placeholder={"app/src/App.tsx\ndocs/It's a note, final.md"}
            />
            <small>
              One complete path per line — spaces, commas and apostrophes are
              kept.
            </small>
          </label>
        )}
        {task === "commit" && (
          <label>
            Commit message
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Summarize the change"
            />
          </label>
        )}
      </div>
      <CommandBlock
        command={command}
        placeholder="Fill the required fields to build the command."
      />
    </ToolGroup>
  );
}

export function DeveloperTools() {
  const repos = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api<Repo[]>("/repositories"),
  });
  return (
    <div className="page tools-page">
      <Heading
        title="CLI & MCP."
        description="Build a GraphPilot CLI command, copy it and run it in your terminal. Commands run from a GraphPilot checkout with uv and Git installed — the browser never executes them."
      />
      <BackendStatus />
      <section className="tools-setup" aria-label="CLI sign-in">
        <div>
          <h2>Sign the CLI in</h2>
          <p>
            Approves this terminal in your browser, then saves a private
            credential in your CLI config — nothing is stored here.{" "}
            <code>--write</code> is required to ask questions or cancel jobs;
            read-only sign-in is enough for repository search and job lists.
          </p>
        </div>
        <CommandBlock
          command={`${CLI} login --server ${q(location.origin)} --write`}
          placeholder=""
        />
      </section>
      <div className="tools-grid">
        {repos.isPending ? (
          <section className="tool-group">
            <Loading label="Loading repositories…" />
          </section>
        ) : repos.error ? (
          <section className="tool-group">
            <ErrorNotice
              error={repos.error}
              retry={() => void repos.refetch()}
            />
          </section>
        ) : (
          <CodeQuestions repos={repos.data} />
        )}
        <CloudRunner />
        <DailyGit />
      </div>
      <p className="tools-footnote">
        <FolderGit2 size={14} />
        This page builds commands — the explicit CLI operations you run act on
        the machine you choose. Indexing and questions never execute repository
        code, and this page never sees your GitHub or CLI credentials.
      </p>
    </div>
  );
}
