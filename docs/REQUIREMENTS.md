# PROJECT: GRAPHPILOT — Full-Stack AI Code Intelligence Platform

## ROLE

You are a principal full-stack engineer, software architect, database engineer, AI systems engineer, security engineer, and QA engineer.

Your task is to **design, implement, integrate, test, and verify a complete working web application called GraphPilot**.

GraphPilot is an evidence-aware AI code intelligence platform built around FalkorDB.

The application connects source code, GitHub repositories, functions, dependencies, commits, pull requests, issues, CI/CD runs, logs, tests, and historical decisions into a unified graph.

Users interact with the graph through a visual web interface and an AI agent.

**You are working inside the project repository already opened in the terminal. Inspect the existing repository before making architectural decisions.**

Do not simply explain how to build the project. Actually implement it.

---

# 1. NON-NEGOTIABLE ENGINEERING RULES

1. Build actual working functionality, not merely UI mockups.
2. Inspect the existing codebase, dependencies, scripts, architecture, and tests before modifying anything.
3. Prefer reusing proven implementations over rewriting existing functionality.
4. Work in small, verifiable implementation phases.
5. After every phase, run relevant tests and resolve failures before continuing.
6. Do not claim a feature works without verifying it.
7. Do not invent API responses, database records, successful test results, or AI answers.
8. Do not use mock backend data in production features. Synthetic fixtures are permitted in automated tests and explicitly labeled demo mode.
9. Prioritize clean architecture, low resource usage, maintainable code, and minimal application overhead.
10. Avoid unnecessary abstractions, duplicate services, excessive dependencies, and overengineering.
11. Never expose database credentials, LLM keys, GitHub tokens, or admin secrets to the frontend.
12. Enforce permissions in the backend, not just by hiding frontend buttons.
13. Keep existing working features intact where possible.
14. Implement meaningful loading states, failure states, retries, validation, and error messages.
15. Document unsupported functionality instead of pretending it works.
16. Do not execute arbitrary AI-generated terminal commands or automatically alter user repositories without explicit permission.
17. Use safe defaults and least-privilege access throughout the application.
18. Maintain a running implementation checklist and testing report.

When a test fails, investigate and fix the underlying issue. Do not disable or weaken tests merely to obtain a passing result.

---

# 2. EXISTING CODEBASE INVESTIGATION

First inspect the current working directory.

Check:

- Directory structure and existing source code.
- Git status and current branch.
- Frontend and backend frameworks.
- Package manifests and lockfiles.
- Existing environment configuration.
- Database connectivity.
- Existing GraphRAG and FalkorDB integrations.
- Authentication and permission implementations.
- Unit, integration, and E2E tests.
- Available CPU, memory, disk, ports, and development tools.

Evaluate the official project:

https://github.com/FalkorDB/code-graph

Its existing implementation may provide:

- FastAPI backend.
- React and Vite frontend.
- FalkorDB integration.
- Code analyzers.
- Code graph visualization.
- Existing GraphRAG functionality.
- MCP and CLI tools.
- Docker infrastructure.

Inspect actual checked-out source code before relying on any specific capability.

Do not assume every programming language, incremental indexing feature, or multi-branch feature is already implemented.

If appropriate, extend the existing CodeGraph architecture. If the current repository is empty, establish a clean project structure. Do not destructively overwrite an unrelated existing project.

Document reused components, added components, and known upstream limitations.

**Verification Gate 0**

- Existing project successfully inspected.
- Architecture decisions documented.
- Application baseline runs, if an application exists.
- Existing tests executed where possible.
- Pre-existing failures distinguished from new failures.

---

# 3. TECHNOLOGY STACK

Prefer:

**Frontend**
- React
- Vite
- TypeScript
- Tailwind CSS
- shadcn/ui or Radix UI
- Lucide icons
- TanStack Query for server state
- React Router if routing is not already available
- Existing graph visualization library, or Cytoscape.js if necessary

**Backend**
- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy and Alembic for relational metadata
- FalkorDB Python client
- Existing CodeGraph analyzers
- GitPython or carefully controlled Git subprocesses
- httpx for external requests

**Data storage**
- FalkorDB: knowledge graph.
- PostgreSQL: users, sessions, permissions, repository metadata, jobs, audit records.
- Git repositories: authoritative code history.
- Persistent filesystem/object storage: logs and large artifacts.

**AI**
- Existing LiteLLM integration if suitable.
- Configurable local OpenAI-compatible inference endpoint, including llama.cpp servers.
- Optional hosted LLM providers.
- A non-LLM graph search mode that works without API keys.

**Development and testing**
- Docker Compose
- uv and npm
- Ruff
- TypeScript compiler
- pytest
- Playwright
- GitHub Actions for project CI

Pin compatible dependency versions using lockfiles.

Avoid introducing Next.js, an additional Node backend, extra message brokers, or microservices unless they solve a concrete problem that cannot reasonably be handled by the existing stack.

---

# 4. HIGH-LEVEL SYSTEM ARCHITECTURE

Implement the following logical structure:

```text
                        USER
                         |
                React Web Application
                         |
                  FastAPI Backend
                         |
              Authentication + RBAC
                         |
               Application Services
                         |
       +-----------------+-----------------+
       |                 |                 |
  Repository         Search + AI       Admin Services
  Ingestion          Retrieval         + Audit
       |                 |                 |
  Parser / Git       Graph Queries     Job Management
       |                 |                 |
       +---------- FalkorDB --------------+
       |
  GitHub History / Issues / PRs / CI
       |
  Persistent Files and Log Storage

PostgreSQL: Users, permissions, repository ownership,
sessions, indexing jobs, sync state, audit records.
```

Use clear boundaries between:

- API routes.
- Authentication and authorization.
- Repository ingestion.
- Graph indexing.
- Graph queries.
- Search ranking.
- Agent orchestration.
- Persistent storage.
- Background workers.
- Administrative operations.

Do not allow the LLM to communicate with FalkorDB using unrestricted database credentials or arbitrary user-generated Cypher.

---

# 5. PHASE 1 — DEVELOPMENT INFRASTRUCTURE

Implement a reproducible local development environment.

Services:

1. Frontend.
2. FastAPI backend.
3. FalkorDB.
4. PostgreSQL.
5. A persistent indexing/synchronization worker, if needed.

Requirements:

- Docker Compose configuration.
- Persistent database volumes.
- Database readiness checks.
- Environment-variable validation.
- Example configuration file.
- Automated database migrations.
- Application health endpoints.
- Clear startup/shutdown behavior.
- Structured logging.
- Development and production configurations.

Use a durable PostgreSQL-backed job table or another justified lightweight queue mechanism. Avoid fragile in-process-only indexing jobs for long operations.

Provide straightforward commands for installation, startup, testing, and shutdown.

The application must not require a paid cloud account or paid LLM API for basic graph indexing and search.

**Verification Gate 1**

- All required services start.
- Frontend communicates with backend.
- Backend connects to FalkorDB.
- Backend connects to PostgreSQL.
- Database data survives container restarts.
- Health checks work.
- No startup secrets are exposed.

---

# 6. PHASE 2 — AUTHENTICATION AND AUTHORIZATION

Create a complete user authentication system.

Features:

- Register.
- Login.
- Logout.
- Current-session retrieval.
- Protected routes.
- Secure password storage using Argon2id.
- Session expiration.
- Password reset using secure one-time tokens when an outbound email provider is configured.
- Clear handling for unavailable email delivery.
- Admin-managed account disabling.
- Audit logging for sensitive actions.

Use secure HttpOnly session cookies, appropriate SameSite settings, CSRF protection, and Secure cookies in HTTPS deployments.

Use one authentication system with roles:

**User**
- Access their authorized repositories.
- Create indexing jobs for permitted repositories.
- Ask AI questions.
- Explore allowed graphs.
- View permitted history and analysis reports.
- Manage their own account.

**Admin**
- Manage accounts and roles.
- Manage repository ownership and access.
- Inspect indexing jobs and system health.
- Configure permitted application-level settings.
- View audit logs.
- Perform explicitly authorized maintenance.

Admin access must not silently bypass auditing or expose other users' secrets.

Create a safe initial-admin bootstrap command. Do not ship hardcoded credentials.

Enforce repository membership on every relevant API operation, including graph traversal, evidence retrieval, artifacts, downloads, and AI tool calls.

Secure or remove legacy shared-token/public-access routes that bypass the new permission model.

**Verification Gate 2**

Automated tests must prove:

- Registration and login work.
- Invalid credentials are rejected.
- Logout invalidates the session.
- Users cannot open admin APIs.
- Users cannot access other users' private repositories.
- Disabled accounts lose access.
- Expired sessions are rejected.
- CSRF protections work.
- Database secrets never appear in browser responses.

---

# 7. PHASE 3 — COMPLETE FRONTEND WEBSITE

Build a polished, modern, responsive developer platform.

Design direction:

- Premium SaaS application.
- Clean, minimal and professional.
- Dark and light themes.
- Excellent typography.
- Consistent spacing and component hierarchy.
- Tasteful animations.
- Clear hover, focus, loading, error and disabled states.
- Responsive desktop, tablet and mobile layouts.
- Accessible forms and keyboard navigation.

Avoid generic, cluttered, over-designed AI dashboards.

### Required pages

**A. Public Landing Page**

Include:
- Product explanation.
- Interactive or clearly labeled illustrative graph preview.
- Core capabilities.
- Architecture overview.
- Getting-started guide.
- Login and registration buttons.

**B. Login / Signup**

Provide complete form validation, helpful error messages, session handling, and authenticated redirects.

**C. User Dashboard**

Include:
- Connected repository cards.
- Indexing status.
- Graph statistics.
- Recent queries.
- Recent CI failures when available.
- Quick actions.
- Recent activity.

All metrics must come from actual data.

**D. Connect Repository**

Support:
- Public GitHub repository URL.
- Explicitly permitted server-local repository path in local deployment.
- Optional user-approved project ZIP upload.

Do not pretend a cloud website can directly access arbitrary folders on a visitor's computer.

For remote users' local repositories, provide a secure upload or explicitly documented local CLI/companion integration.

**E. Repository Overview**

Show:
- Repository name and branch.
- Last indexed commit.
- Indexing status.
- File/function/class counts.
- Connected GitHub history.
- Graph quality metrics.
- Available analysis actions.

**F. Graph Explorer**

Provide:
- Interactive graph.
- Zoom and pan.
- Node selection.
- Relationship highlighting.
- Node and edge filters.
- Search by symbol/file.
- Expand neighbors.
- Optional relationship depth.
- Node details and evidence panel.
- Jump to source file and line.

Use bounded graph queries and progressive rendering. Never download and render an entire large graph by default.

**G. AI Context Explorer**

Provide:
- Chat interface.
- Repository and branch selection.
- Conversation history.
- Loading/streaming response states where supported.
- Graph path explanation.
- File and line citations.
- Referenced commits, issues and PRs.
- Missing-evidence warnings.
- Retrieval diagnostics.

Show useful graph search results even when no LLM is configured.

**H. History and Timeline**

Show connected:
- Issues.
- Pull requests.
- Commits.
- CI runs.
- Relevant decisions.

Support filtering and navigation between related entities.

**I. Analysis / Impact Report**

Allow the user to select a file or function and inspect potential downstream impact.

Distinguish:
- Verified direct dependencies.
- Possible indirect impact.
- Unknown or unverified relationships.

**J. Tests and Diagnostics**

Display:
- Indexing validation status.
- Graph integrity checks.
- Ingestion failures.
- Recent test results when connected.
- Query performance metrics.
- Evidence completeness.

Do not label a system secure or healthy unless appropriate checks support that claim.

**K. User Settings**

Profile, preferences, theme, active sessions, connected providers, and permitted repository settings.

**L. Admin Dashboard**

Implement actual functional interfaces for:
- User management.
- Role changes.
- Repository access management.
- Indexing and sync jobs.
- Failed-job retries.
- System health.
- Audit logs.
- Basic configuration and diagnostics.

Every visible interactive control must work or be clearly marked unavailable.

**Verification Gate 3**

Run Playwright browser tests for:
- Navigation.
- Login.
- Responsive layouts.
- Dashboard.
- Repository connection.
- Graph interaction.
- User/admin restrictions.
- Settings.
- Error and empty states.

Capture screenshots for visual inspection and correct layout defects.

---

# 8. PHASE 4 — REPOSITORY INGESTION

Implement one unified ingestion interface with separate adapters.

Supported ingestion sources:

1. Server-local Git repositories in explicitly allowed directories.
2. Public GitHub repositories.
3. Explicitly uploaded source archives.

Private GitHub repository support may be added through a securely configured GitHub App with minimum necessary permissions. Never assume an arbitrary submitted GitHub URL grants access.

For each repository:

- Validate the source.
- Normalize identity.
- Determine branch and commit SHA.
- Apply file ignore rules.
- Exclude binary files and dependency directories.
- Enforce file count, archive size, extraction and execution limits.
- Parse supported programming languages.
- Extract files, classes, functions, and relationships.
- Store source references.
- Record indexing metadata.
- Report progress and failures.

Prefer existing proven analyzers.

Initially guarantee correct Python indexing. Expand to other languages only after verifying parser support.

Avoid executing repository code merely to index it.

Protect cloning and archive extraction against:
- Path traversal.
- Symlink escape.
- SSRF.
- Unsupported protocols.
- Unbounded downloads.
- Resource exhaustion.

**Verification Gate 4**

Use a small fixture repository with known functions, imports, commits, and dependencies.

Verify that the graph contains the expected entities and relationships.

Repeated indexing must not create duplicates.

---

# 9. PHASE 5 — GRAPH DATA MODEL

Extend the existing CodeGraph schema without breaking existing functionality.

Required conceptual node types:

- Repository
- Branch
- File
- Function
- Class
- Commit
- PullRequest
- Issue
- WorkflowRun
- TestCase
- LogArtifact
- Decision, when reliable decision evidence exists

Relationships:

- HAS_FILE
- DEFINES
- CALLS
- IMPORTS
- CONTAINS_COMMIT
- MODIFIES
- REFERENCES
- ADDRESSES
- TRIGGERED_BY
- TESTS
- PRODUCES
- RELATED_TO
- SUPERSEDES

The schema should use typed relationships, not a giant unstructured collection of generic connections.

Each relevant node must record:
- Stable ID.
- Repository identity.
- Entity type.
- Original source ID.
- Commit or branch context where applicable.
- Source URL or file reference.
- Relevant timestamps.
- Indexing version.
- Verification/provenance status where meaningful.

Use stable identifiers and uniqueness constraints or equivalent deduplication strategies.

Ensure that historical versions are distinguishable from current versions.

Don't claim a PR fixed an issue merely because it references it.

Choose an explicit isolation strategy for repositories and users. Prefer separate graph namespaces per repository/branch when compatible with CodeGraph, enforced through backend membership checks and database access controls.

Do not use globally mutable graph names based only on display names.

Implement appropriate FalkorDB indexes for common property lookups.

Use parameterized, bounded Cypher queries.

Store large raw code, binary artifacts, and complete log archives outside graph node properties.

**Verification Gate 5**

Tests must validate:

- Correct graph relationships.
- Stable identities.
- Duplicate prevention.
- Branch isolation.
- Repository isolation.
- Missing-node handling.
- Referential integrity rules.
- Safe repeated ingestion.

---

# 10. PHASE 6 — GITHUB HISTORY AND CI/CD INTEGRATION

Integrate GitHub historical context.

Ingest, subject to API access and limits:

- Commits and commit metadata.
- Issues and issue status.
- Pull requests and PR status.
- Pull request commits.
- Relevant changed files.
- GitHub Actions workflow runs.
- Failed jobs and associated metadata.
- Available CI logs and failure summaries.

Use GitHub REST API and local Git history appropriately.

Store original GitHub IDs and URLs.

Maintain relationships between issues, PRs, commits, files, tests, and workflow runs.

Handle:
- Pagination.
- Rate limits.
- Retry-After headers.
- Incremental synchronization.
- Deleted or unavailable resources.
- Duplicate events.
- Interrupted synchronization.

GitHub workflow log download URLs are short-lived. Download promptly when permitted and safely archive selected logs with retention settings and secret redaction.

Do not promise recovery of historical logs that GitHub has already deleted.

Implement synchronization jobs with observable status and bounded retries.

Webhook integration is optional for the first working version; if implemented, validate HMAC signatures before processing events.

**Verification Gate 6**

Using a public test repository or recorded API fixtures, verify:

- Commit ingestion.
- PR and issue linking.
- Workflow-run ingestion.
- Duplicate suppression.
- Rate-limit handling.
- Sync resume.
- Unavailable log behavior.

---

# 11. PHASE 7 — INTELLIGENT GRAPH SEARCH

Create a reusable, deterministic retrieval layer.

Expose these backend operations:

- find_symbol
- get_neighbors
- find_path
- impact_analysis
- search_history
- search_context

Reuse existing CodeGraph operations where available.

Search execution:

**Step 1: Interpret query**

Recognize:
- Function names.
- Filenames.
- Issue numbers.
- PR numbers.
- Commit SHA.
- Dependency questions.
- Change-impact questions.
- CI failure questions.

**Step 2: Retrieve candidates**

Use:
- Exact property lookup.
- Full-text search.
- Bounded graph traversal.
- Historical metadata lookup.

Semantic/vector search is optional and should not be a prerequisite for the first functioning version.

**Step 3: Rank evidence**

Use a small, transparent scoring policy considering:
- Match relevance.
- Relationship distance.
- Source reliability.
- Repository/branch compatibility.
- Recency where relevant.
- Direct verification.

Do not let recency automatically override the user's explicitly requested historical revision.

**Step 4: Retrieve source evidence**

Read exact code regions, issue descriptions, commit diffs, or log excerpts when necessary.

**Step 5: Return structured results**

Each result should include:
- Entity ID and type.
- Relationship explanation.
- Evidence source.
- Source URL/path/line when available.
- Current versus historical status.
- Retrieval score and its meaning.
- Any significant uncertainty.

Strictly limit graph depth, returned nodes, processing time, and query cost.

Use deterministic query templates rather than unrestricted LLM-generated Cypher for initial retrieval.

**Verification Gate 7**

Use a fixed benchmark set with known expected answers.

Test direct symbol searches, dependencies, issue-to-commit links, failed CI analysis, unrelated-entity filtering, missing data, and tenant isolation.

Report retrieval correctness, latency, number of graph queries and context size.

---

# 12. PHASE 8 — AI AGENT INTEGRATION

Build an AI assistant that uses graph evidence rather than blindly guessing.

Support both:
- Local OpenAI-compatible endpoints, including llama.cpp.
- Configurable hosted model providers.

Never require an LLM for deterministic graph exploration.

Agent workflow:

1. Receive the user's question.
2. Identify the repository and permitted context.
3. Search the graph.
4. Inspect the returned relationships.
5. Determine whether evidence is sufficient.
6. Retrieve specific source files/logs when insufficient.
7. Synthesize an answer with citations.
8. State limitations or unknown facts.
9. Optionally propose a change without automatically applying it.

Implement a bounded retrieval budget:
- Limited tool calls.
- Limited graph traversal depth.
- Limited context tokens.
- Limited retries.
- Configurable operation timeout.

The AI should avoid repeated searches that contribute no new information.

Treat source-code comments, issues, PR descriptions, logs, and external text as untrusted data. They must not override system instructions or tool permissions.

AI answers must explain:
- What evidence was found.
- Which graph relationships were followed.
- Why the conclusion is plausible.
- What remains unverified.
- What should be checked before modifying code.

If no LLM endpoint is configured, provide genuine structured graph results with a clear notice that natural-language synthesis is unavailable.

**Verification Gate 8**

Evaluate the agent against known tasks, including:

- Find the callers of a function.
- Explain a dependency chain.
- Investigate an issue.
- Identify files modified by a PR.
- Identify evidence related to a failing CI test.
- Determine when the graph lacks sufficient information.

No fabricated source references or fake successful tool calls.

---

# 13. PHASE 9 — INCREMENTAL UPDATES

Implement cost-aware graph maintenance.

Track:
- Repository ID.
- Branch.
- Commit SHA.
- File path.
- Content hash.
- Parser version.
- Last indexed time.

On synchronization:
- Identify additions, modifications and deletions.
- Skip unchanged files.
- Reparse modified files.
- Update changed nodes and relationships.
- Invalidate affected retrieval caches.
- Preserve historical relationships where required.
- Avoid leaving stale active relationships.

Use idempotent job execution.

Handle renamed files, changed symbols, interrupted indexing and conflicting synchronization jobs.

If accurate incremental updates are unsupported by a reused analyzer, implement and test the necessary behavior rather than declaring it complete.

**Verification Gate 9**

Modify one file in a fixture repository.

Confirm unchanged files are skipped, affected graph records are updated correctly, deleted relationships are cleaned up, and a second unchanged scan performs no redundant writes.

---

# 14. PHASE 10 — ADMINISTRATION AND MONITORING

Finish the admin interface and backend.

Provide real metrics for:
- Users.
- Repositories.
- Graph entities.
- Indexing jobs.
- Sync failures.
- Query latency.
- Application errors.
- Storage usage where measurable.

Admin actions must be protected and audited.

Provide retry/cancel operations for jobs when safe.

Prevent multiple workers from accidentally processing the same job concurrently.

Use clear application-level permissions rather than relying on the frontend to prevent restricted actions.

Keep maintenance commands and dangerous DB operations inaccessible to ordinary users.

**Verification Gate 10**

Automated tests must prove unauthorized users cannot access administrative resources, and permitted actions change real backend state.

---

# 15. PHASE 11 — COMPREHENSIVE TESTING

Implement layered testing.

### Unit tests

Cover:
- Schema validation.
- Entity IDs.
- Graph query construction.
- Search ranking.
- Permissions.
- Configuration.
- File hash comparisons.

### Integration tests

Use a real isolated FalkorDB and PostgreSQL test environment.

Verify:
- Graph creation.
- Ingestion.
- Search.
- Deletion.
- Sync.
- Authentication.
- Job processing.

### End-to-end tests

Use Playwright against the real running application.

Required user journey:

1. Register an account.
2. Log in.
3. Connect a public test repository.
4. Start indexing.
5. Observe real progress.
6. Open the graph.
7. Search for a known function.
8. Inspect dependencies.
9. Ask an evidence-based question.
10. Open linked source evidence.
11. Log out.
12. Verify protected pages are no longer accessible.

Required admin journey:

1. Log in as admin.
2. View users and repository jobs.
3. Change a test user's permission.
4. Confirm the permission change is enforced.
5. Inspect the recorded audit event.

### Security tests

Test:
- Broken object-level authorization.
- Unauthorized graph queries.
- Cross-repository data access.
- CSRF.
- Injection attempts.
- Unsafe file paths.
- ZIP extraction attacks.
- Untrusted GitHub URLs.
- Malicious repository content.
- Agent prompt injection.
- Sensitive log leakage.
- Secrets in API responses.

### Performance tests

Measure:
- Graph query p50/p95 latency.
- Concurrent API requests.
- Repository indexing duration.
- Memory and CPU usage.
- Database restart/recovery.
- Graph explorer rendering behavior.

Suggested initial load test: 20 concurrent users on a small reference repository.

Establish baselines first. Treat performance targets as goals, not guaranteed results.

### Regression tests

Test major functionality again after integrations are complete.

Add GitHub Actions CI covering linting, type-checking, backend tests, and relevant integration/E2E checks.

**Verification Gate 11**

Produce a test report stating:
- Tests executed.
- Tests passed.
- Tests failed.
- Tests skipped and why.
- Performance measurements.
- Known security limitations.
- Unsupported capabilities.

Never report success for tests not actually run.

---

# 16. PHASE 12 — PRODUCTION READINESS AND FINAL VERIFICATION

Prepare the application for deployment.

Requirements:

- Multi-stage or otherwise optimized container builds.
- Production environment documentation.
- Persistent volumes.
- Database migrations.
- Reliable service restart behavior.
- Health checks.
- Security headers.
- CORS restrictions.
- HTTPS deployment guidance.
- Backup/restore instructions.
- Log retention controls.
- Secret management.
- Dependency audit.
- Cleanup of development-only endpoints.

Do not expose PostgreSQL or FalkorDB directly to the public internet.

Ensure source-code and log access is permission-aware.

Provide a `.env.example` without credentials.

Provide an accurate README covering:
- Prerequisites.
- Installation.
- Development startup.
- Production startup.
- Initial admin creation.
- Repository connection.
- FalkorDB setup.
- LLM setup.
- Testing.
- Architecture.
- Troubleshooting.
- Known limitations.

---

# 17. DESIRED PROJECT ORGANIZATION

Preserve the existing project organization where appropriate.

Aim for these logical modules, not necessarily these exact directories:

```text
graphpilot/
├── app/                   # React frontend
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── features/
│       ├── hooks/
│       └── lib/
├── api/                   # FastAPI backend
│   ├── auth/
│   ├── routes/
│   ├── services/
│   ├── ingestion/
│   ├── graph/
│   ├── search/
│   ├── agent/
│   ├── models/
│   └── workers/
├── migrations/
├── tests/
├── e2e/
├── fixtures/
├── docs/
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

Avoid moving or rewriting upstream CodeGraph modules unnecessarily.

The architecture should remain understandable to a new contributor.

---

# 18. DEFINITION OF DONE

The project is complete only when:

- A user can register and log in.
- An admin can securely manage user access.
- A user can connect a supported repository.
- The repository is actually indexed.
- FalkorDB contains valid graph nodes and relationships.
- The graph can be explored visually.
- Graph search returns accurate, scoped results.
- The application can show real source-code evidence.
- Supported GitHub commits, PRs, issues and CI history are connected.
- The AI can answer questions using graph retrieval when a model is configured.
- The app handles an unavailable AI provider without fabricating answers.
- Incremental synchronization is functional.
- Permission isolation is tested.
- UI and backend work together.
- Data persists across restarts.
- Tests and documentation are provided.
- Known incomplete functionality is clearly disclosed.

A beautiful UI without a working backend does not meet the definition of done.

A working backend without a usable interface also does not meet the definition of done.

---

# 19. HOW YOU MUST EXECUTE THIS TASK

**Follow this implementation workflow for every phase:**

1. Inspect relevant current code.
2. Define the smallest working implementation.
3. Implement the feature.
4. Run static checks.
5. Run focused automated tests.
6. Run integration tests where relevant.
7. Validate through actual HTTP requests or browser interactions.
8. Fix discovered problems.
9. Update implementation documentation.
10. Mark the phase verified only after the evidence supports it.

Maintain a file such as `IMPLEMENTATION_STATUS.md` with:

- Phase name.
- Implemented functionality.
- Verification commands.
- Test results.
- Outstanding issues.
- Next steps.

If a required external credential or service is unavailable, finish every independently testable component, show the precise blocker, and never substitute fabricated success.

After completing the implementation, provide:

1. Architecture summary.
2. Implemented features.
3. File/module changes.
4. Exact installation and run commands.
5. Verified test results.
6. Remaining limitations.
7. Deployment instructions.

**Start immediately by inspecting the existing project and implementing Phase 0. Continue progressively through the phases, prioritizing a fully working repository-to-graph-to-search-to-UI path before optional enhancements.**

Do not stop after producing a plan or creating empty scaffolding.

The final goal is a secure, responsive, reliable and genuinely functional graph-powered AI code intelligence website suitable for demonstrating in the FalkorDB hackathon.