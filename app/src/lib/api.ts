export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export type User = {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  theme: "light" | "dark" | "system";
  disabled: boolean;
};
export type Repo = {
  id: string;
  name: string;
  branch: string;
  source_type: string;
  source_url: string | null;
  status: string;
  commit_sha: string | null;
  indexed_at: string | null;
  created_at: string;
  stats: Record<string, unknown>;
  sync_state: Record<string, unknown>;
  snapshot_id: string | null;
  historical: boolean;
  permission: "owner" | "write" | "read" | null;
};
export type Node = {
  id: string;
  name: string;
  type: string;
  path?: string;
  line?: number;
  end_line?: number;
  doc?: string;
  qualified_name?: string;
  provenance?: string;
  commit?: string;
  score?: number;
  score_meaning?: string;
  status?: string;
  url?: string;
  body?: string;
  summary?: string;
  timestamp?: string;
  log_status?: string;
};
export type Edge = {
  id: string;
  source: string;
  target: string;
  type: string;
  line?: number;
  provenance?: string;
};
export type Graph = {
  nodes: Node[];
  edges: Edge[];
  bounded: boolean;
  limit: number;
};
export type Job = {
  id: string;
  repository_id: string;
  branch: string | null;
  kind: string;
  status: string;
  progress: number;
  message: string;
  attempts: number;
  created_at: string;
  finished_at: string | null;
  cancel_requested: boolean;
};
export type Evidence = {
  node: Node;
  content: string;
  start_line: number | null;
  end_line: number | null;
  commit: string;
  url: string | null;
  truncated?: boolean;
  notice?: string;
  download_url?: string;
};
export type Citation = {
  citation: string;
  entity_id: string;
  name: string;
  path?: string;
  start_line: number | null;
  end_line: number | null;
  content: string;
  url: string | null;
  commit: string;
};
export type ContextResult = {
  branch: string;
  snapshot_id: string | null;
  historical: boolean;
  mode: "graph" | "ai";
  answer: string | null;
  notice: string;
  results: Node[];
  relationships: Edge[];
  warnings: string[];
  evidence: Citation[];
  diagnostics: {
    latency_ms: number;
    graph_queries: number;
    returned_nodes: number;
    ranking: string;
  };
  unknowns?: string[];
};
export type Conversation = {
  id: string;
  question: string;
  response: ContextResult;
  created_at: string;
  branch: string;
  snapshot_id: string | null;
};
export type Branches = {
  default_branch: string;
  branches: { branch: string; status: string; commit_sha: string | null }[];
};
export type Snapshot = {
  id: string;
  branch: string;
  commit_sha: string;
  kind: string;
  created_at: string;
  current: boolean;
};
/** Pin reads and evidence links to their actual branch and graph generation. */
export function scoped(
  path: string,
  context: {
    branch?: string | null;
    revision?: string | null;
    snapshot_id?: string | null;
  },
) {
  const [pathname, search = ""] = path.split("?");
  const params = new URLSearchParams(search);
  if (context.branch) params.set("branch", context.branch);
  const revision = context.revision ?? context.snapshot_id;
  if (revision) params.set("revision", revision);
  const query = params.toString();
  return pathname + (query ? "?" + query : "");
}
export type Capabilities = {
  local_sources: boolean;
  llm_configured: boolean;
  password_reset_email: boolean;
  github_authenticated: boolean;
};
export function csrf() {
  return (
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("gp_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") || ""
  );
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRF-Token": csrf(),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = "The request failed. Please try again.";
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail
                .map((e: { msg: string }) => e.msg.replace("Value error, ", ""))
                .join(". ")
            : message;
    } catch {
      /* retain readable fallback */
    }
    throw new ApiError(response.status, message);
  }
  return response.json();
}
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const number = (value: unknown) =>
  typeof value === "number" ? value.toLocaleString() : "—";
export function date(value: string | null | undefined) {
  return value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Not indexed yet";
}
export function safeUrl(value: string | null | undefined) {
  if (!value) return undefined;
  try {
    const u = new URL(value);
    return u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}
