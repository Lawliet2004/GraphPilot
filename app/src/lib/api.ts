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
  /** Exact literal-match position when this node came from a content scan. */
  match?: {
    line: number;
    column: number;
    end_column: number;
    snippet?: string;
    snippet_column?: number;
  };
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
/** A served excerpt that is a bounded character window of one long line. */
export type LineExcerpt = {
  line: number;
  start_column: number;
  end_column: number;
  line_length: number;
  partial: boolean;
};
export type Evidence = {
  node: Node;
  content: string;
  start_line: number | null;
  end_line: number | null;
  commit: string;
  url: string | null;
  truncated?: boolean;
  /** True when the final served line is cut mid-line; null/absent for non-source evidence. */
  end_line_partial?: boolean | null;
  /** Present when one served line is a partial column window of a longer line. */
  line_excerpt?: LineExcerpt | null;
  /** Manifest content hash the served bytes were verified against. */
  content_hash?: string | null;
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
  /** Absent on responses saved before excerpt metadata existed: completeness is unknown. */
  truncated?: boolean;
  /** True when the final served line is cut mid-line; null for non-source evidence. */
  end_line_partial?: boolean | null;
  /** True when the asker pinned this exact source selection. */
  pinned?: boolean;
  /** Present when one served line is a partial column window of a longer line. */
  line_excerpt?: LineExcerpt | null;
  /** Exact literal-match position behind this citation, when known. */
  match?: Node["match"];
  /** Manifest hash the served source bytes were verified against. */
  content_hash?: string | null;
};
export type ContentHit = {
  node_id: string;
  node: Node;
  path: string;
  line: number;
  column: number;
  end_column: number;
  snippet: string;
  snippet_column: number;
  snippet_start_partial: boolean;
  snippet_end_partial: boolean;
  line_length: number;
  /** Manifest hash the matched bytes were verified against. */
  content_hash?: string | null;
};
export type ContentSearch = {
  results: ContentHit[];
  returned: number;
  limit: number;
  /** Exact match count, or null when the scan stopped before finishing. */
  total: number | null;
  /** True only when the whole approved manifest was scanned successfully. */
  scan_complete: boolean;
  truncated: boolean;
  has_more: boolean;
  completion_reason: string;
  scan: {
    files_scanned: number;
    files_skipped: number;
    skip_reasons: Record<string, number>;
    bytes_scanned: number;
    elapsed_ms: number;
    manifest_entries: number;
    manifest_incomplete: boolean;
  };
  graph_queries: number;
  scope: {
    branch: string;
    snapshot_id: string | null;
    commit: string;
    historical: boolean;
    manifest: string;
    case_sensitive: boolean;
    filters?: { path?: string | null; suffix?: string | null };
  };
};
export type RepoPage = {
  repositories: Repo[];
  limit: number;
  offset: number;
  returned: number;
  has_more: boolean;
  next_offset: number | null;
};
export type ImpactResult = {
  results: { node: Node; distance: number; classification: string }[];
  unknown: string;
  max_depth?: number;
  returned?: number;
  limit?: number;
  /** Exact reachable-caller count within depth; null when traversal stopped early. */
  total?: number | null;
  truncated?: boolean;
  /** False when a bounded stop interrupted exploration of a caller layer. */
  traversal_complete?: boolean;
  has_more?: boolean;
  completion_reason?: string;
};
export type ContextResult = {
  branch: string;
  snapshot_id: string | null;
  historical: boolean;
  mode: "graph" | "ai";
  provider?: string;
  model?: string;
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
  byok_available: boolean;
  password_reset_email: boolean;
  github_authenticated: boolean;
};
export type ModelCredentialStatus = {
  configured: boolean;
  provider: "openai" | "openrouter" | null;
  model: string | null;
  updated_at: string | null;
  byok_available: boolean;
  providers: string[];
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
function unavailable(status: number) {
  return `The GraphPilot backend is unavailable (HTTP ${status}). Check your connection — if the Codespace runner is stopped, start it, then retry.`;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
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
  } catch {
    // Network-level failure: the API origin is unreachable, not a bad request.
    throw new ApiError(
      0,
      "The GraphPilot backend could not be reached. Check your connection — if the Codespace runner is stopped, start it, then try again.",
    );
  }
  if (!response.ok) {
    let message: string | undefined;
    let parsed = false;
    try {
      const body = await response.json();
      parsed = true;
      message =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail
                .map((e: { msg: string }) => e.msg.replace("Value error, ", ""))
                .join(". ")
            : undefined;
    } catch {
      /* gateway or proxy responses are often HTML; never echo raw bodies */
    }
    message ??= [502, 503, 504].includes(response.status)
      ? unavailable(response.status)
      : parsed
        ? "The request failed. Please try again."
        : `The server returned an unreadable response (HTTP ${response.status}). Try again in a moment.`;
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  try {
    return await response.json();
  } catch {
    throw new ApiError(
      response.status,
      "The server returned an unreadable response. Try again in a moment.",
    );
  }
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
