# ForgeAI — Implementation Status

## 1. Purpose

This document records what is actually built in the repository today and
how it differs from the design in documents 01–06.

Documents 01–06 describe the intended product and architecture.
This document describes the as-built system, so the two can be kept in
agreement.

It covers:

- What is implemented per service
- Where the code differs from the design documents
- Known issues found while reviewing the code
- What remains to be built

---

# 2. Summary

    Design vertical slice                      Status
    ─────────────────────────────────────────────────
    Register / Login                           Built
    Create Organization                        Built
    Connect GitHub (GitHub App)                Built
    Select and connect repository              Built
    Repository synchronization (Kafka→Worker)  Built
    Repository knowledge (chunk + embed)       Built
    Ask questions about repository (RAG)       Built in API, not in UI
    AI Code Review                             Not started
    Test Assistance                            Not started
    Observability / Kubernetes / AWS           Not started

The first half of the MVP flow (register through repository knowledge)
works end to end. The AI Service exists but is not yet wired into the
local environment or the frontend, and retrieval has an isolation
mismatch described in section 8.

---

# 3. Repository Layout (as built)

    ForgeAI/
    ├── Frontend/              React + TypeScript + Vite + Tailwind
    ├── Services/
    │   ├── api/               User / Organization service      (port 8000)
    │   ├── repository/        GitHub + repository service      (port 8001)
    │   ├── ai/                Engineering Agent / conversations (port 8002)
    │   └── worker/            Kafka consumer, indexing pipeline
    ├── docs/                  Design documents 01–07
    ├── Infrastructure/        Empty
    ├── docker-compose.yml
    ├── Makefile
    └── .github/workflows/ci.yml

Differences from the design layout (Service Design §21):

- Folder names are capitalised (`Services`, `Frontend`, `Infrastructure`).
- There is no `scripts/` or top-level `tests/` folder. Tests live inside
  each service.
- `Infrastructure/` exists but is empty.

---

# 4. Services

## 4.1 API Service (User / Organization)

Location: `Services/api`

Built:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login` (OAuth2 password form, returns a JWT)
- `GET  /api/v1/users/me`
- `POST /api/v1/organizations`
- `GET  /api/v1/organizations`
- `GET  /api/v1/organizations/{org_id}`
- `GET  /api/v1/organizations/{org_id}/members`
- `POST /api/v1/organizations/{org_id}/members`
- `PATCH /api/v1/organizations/{org_id}/members/{user_id}/role`

Implementation notes:

- FastAPI, SQLAlchemy 2.x, PostgreSQL (psycopg), bcrypt, python-jose.
- Passwords are stored as bcrypt hashes.
- Tables are created on startup with `Base.metadata.create_all`.
  There are no Alembic migrations yet.
- Organization membership and role checks are implemented as FastAPI
  dependencies (`get_org_membership`, `require_roles`).
- Request-ID middleware is present.
- Tests: auth, organizations, security, users.

## 4.2 Repository Service

Location: `Services/repository`

Built:

- GitHub App install URL, signed `state` token, and callback
- GitHub connection status
- Listing repositories available to the installation
- Connect / list / get / disconnect repository
- Manual sync request and sync status polling
- GitHub webhook receiver with `X-Hub-Signature-256` validation
- Webhook handling for `installation.deleted`,
  `installation_repositories.removed`, and `push`
- Kafka producer for repository events

Implementation notes:

- Tables owned: `github_installations`, `repositories`,
  `repository_syncs`.
- Repository status values: `connecting`, `syncing`, `indexing`,
  `ready`, `failed`, `access_revoked`, `disconnected`.
- A second sync cannot be queued while one is queued or running (409).
- `KAFKA_ENABLED=false` switches the producer to a logging stub.
- A new Kafka producer is created for every publish call.
- A failed publish is logged and the event is dropped; the sync record
  stays `queued`.
- Pull request webhooks are received but not acted on yet.
- Tests: GitHub and repository endpoints.

## 4.3 Worker Service

Location: `Services/worker`

Built:

- Kafka consumer for `repository.connected`,
  `repository.sync.requested`, `repository.disconnected`, and
  `repository.access.revoked`
- Sync pipeline: installation token → shallow clone → file discovery →
  classification → checksum change detection → chunking → embeddings
  → Qdrant upsert → knowledge metadata in PostgreSQL → cleanup
- Idempotency check on sync records (running or completed syncs are
  skipped)
- Removal of vectors and metadata when a repository is disconnected or
  access is revoked
- Tests: chunker and file filter

Implementation notes:

- Tables owned: `repository_files`, `repository_knowledge`.
- The worker reads `repositories`, `repository_syncs`, and
  `github_installations` through mirror models. The Repository Service
  remains the owner of those tables.
- Embeddings use OpenAI `text-embedding-3-small` (1536 dimensions).
- Chunk size is 512 tokens with 64 tokens of overlap.
- Unchanged files (same checksum) are not re-embedded on later syncs.
- Progress counters on the sync record are updated every 10 files.

## 4.4 AI Service

Location: `Services/ai`

Built:

- `POST /api/v1/organizations/{org_id}/conversations`
- `GET  /api/v1/organizations/{org_id}/conversations`
- `GET  /api/v1/conversations/{conversation_id}`
- `DELETE /api/v1/conversations/{conversation_id}`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `GET  /api/v1/conversations/{conversation_id}/messages/stream` (SSE)
- `GET  /api/v1/agent-runs/{agent_run_id}`

Implementation notes:

- The Engineering Agent embeds the question, searches Qdrant, builds a
  system prompt from the retrieved chunks (6,000-token context budget,
  top 8 chunks), and calls OpenAI (`gpt-4o-mini`, temperature 0.2).
- Tables owned: `conversations`, `messages`, `agent_runs`.
- Each run records retrieved chunk IDs and total tokens.
- IDs in this service are UUID strings. The API and Repository services
  use integer IDs (see section 6).
- No tests yet.
- Code Review and Testing agents exist only as enum values.

## 4.5 Frontend

Location: `Frontend`

Built pages & modules:

- Landing page with live capability tabs and interactive architecture showcase
- Login, Register (ForgeAI engineering theme, password strength)
- Organization setup (workspace slug & tenancy setup)
- Dashboard (workspace stats, quick navigation, repository & team health)
- Repositories (GitHub App connect banner, add-repository modal,
  status badges, sync progress bar, manual sync, disconnect)
- GitHub App callback handler
- AI Workspace (conversation list, filter by repo, token-by-token streaming,
  rich markdown rendering with syntax-styled code blocks and 1-click copy)
- AI Code Reviews (open pull requests selector, trigger review, review summary,
  overall score, severity breakdown, finding cards with line numbers and recommendations)
- Code Review Detail view (categorized findings, diff lines, severity filters)
- Test Assistance (target file or PR selector, framework selection, custom instructions,
  synthesized test suite with copy support)
- Feature Planner (LangGraph autonomous plan generation, affected files,
  task sequence, Human-in-the-Loop Approve / Reject / Request Changes workflow)
- Team & Members page (member list, role management, email invitations, workspace summary)
- Complete API client modules: `aiApi`, `reviewsApi`, `pullRequestsApi`, `plansApi`, `organizationsApi`, `repositoryApi`

---

# 5. Local Environment

`docker-compose.yml` runs:

    PostgreSQL, Zookeeper, Kafka, Kafka UI, Qdrant,
    api, repository, worker, frontend

Not in the compose file:

- The AI Service (port 8002)
- Redis
- Elasticsearch, Kibana, Prometheus, Grafana, OpenTelemetry

`Makefile` provides shortcuts for starting, stopping, logs, service
tests (worker and repository only), `psql`, and Kafka topic listing.
There are no Makefile targets for the AI or API tests.

---

# 6. Differences Between the Design Docs and the Code

## 6.1 Roles (Data Model §6, Service Design §4.1)

Design: `OWNER` and `MEMBER`.

Code: `company_admin`, `hr_admin`, `it_admin`, `manager`, `employee`.
These roles come from an earlier onboarding-product design (the code
and CI still say "FlowForge"). The creator of an organization becomes
`company_admin`. `POST .../members` always assigns `employee` and
ignores the role in the request.

Decision needed: keep the design roles and simplify the code, or update
the docs to match the code.

## 6.2 Identifiers

Design: opaque IDs (`"id": "..."`).

Code: integers in the API and Repository services, UUID strings in the
AI Service. The AI Service stores `org_id` and `repository_id` as
strings, while the Worker stores them as integers in Qdrant payloads.

## 6.3 Organization creation (API Design §9)

Design request: `name`, `description`.

Code request also requires `slug`, which must be unique (409 if taken).

## 6.4 Authentication (API Design §5–8)

- Login returns `{ "access_token", "token_type" }`, not a `user` object.
- Login takes an OAuth2 form (`username` is the email), not JSON.
- Register returns `{ "status": "User Created Successfully" }`.
- `POST /auth/logout` is not implemented.
- `GET /users/me` does not return the user's organizations.
- The JWT contains only `sub` and `exp`. It has no organization claim.

## 6.5 Error format (API Design §40)

Design: `{ "error": { "code", "message", "request_id" } }`.

Code: FastAPI's default `{ "detail": "..." }`. Request IDs are generated
by middleware but are not part of the error body.

## 6.6 Gateway and base URLs

Design: one API Gateway in front of all services.

Code: no gateway. The frontend calls the API (8000) and Repository
(8001) services directly. Routing depends on the Vite proxy in
development and the nginx configuration in the frontend container.

## 6.7 Endpoint differences

Built but not in the design:

- `PATCH /organizations/{org_id}/members/{user_id}/role`
- `POST /github/webhook`
- `DELETE /conversations/{conversation_id}`
- `GET /conversations/{id}/messages/stream`

In the design but not built:

- `POST /auth/logout`
- `GET /jobs/{job_id}`
- All pull request and code review endpoints
- Pagination envelope (`items`, `page`, `limit`, `total`) —
  conversations use `{ conversations, total }`

## 6.8 Data model

Built tables: `users`, `organizations`, `memberships`,
`github_installations`, `repositories`, `repository_syncs`,
`repository_files`, `repository_knowledge`, `conversations`,
`messages`, `agent_runs`.

Not built: `tool_calls`, `pull_requests`, `code_reviews`,
`review_findings`, `jobs`.

Other differences:

- Sync tracking uses `repository_syncs` as the job record. There is no
  generic `jobs` table.
- `messages.role` has only `USER` and `ASSISTANT` (no `SYSTEM` or
  `TOOL`).
- `agent_runs` stores retrieved chunk IDs as a comma-separated string.
- Repository knowledge rows store the chunk text as well as metadata.

## 6.9 Events

Built topics: `repository.events`, `repository.sync`.

Not built: `repository.sync.started/completed/failed`,
`repository.indexing.*`, `pull_request.events`, `ai.jobs`,
`code_review.jobs`. The worker updates sync state directly in
PostgreSQL instead of publishing completion events.

## 6.10 Repository status flow

Design: `SYNCING → INDEXING → READY`.

Code: the worker sets `SYNCING`, processes and embeds all files, then
sets `INDEXING` and `READY` back to back. `INDEXING` is therefore not a
meaningful intermediate state yet.

---

# 7. Known Issues

These were found by reading the code. They have not been confirmed by
running the system.

## 7.1 Retrieval will not match indexed data (high)

The Worker writes Qdrant payload keys `organization_id` and
`repository_id` as integers.

The AI Service filters on `org_id` and `repository_id` as strings.

Because the key name and value type both differ, the tenant filter
should match nothing, and the Engineering Agent would answer with
"No relevant code found". The two services need one agreed payload
contract.

## 7.2 AI Service does not verify organization membership (high)

- The `org_id` in the URL is compared to a token claim that the API
  Service never issues, so the check never runs.
- `repository_id` is taken from the request body and is not checked
  against the organization or the user's membership.

Once 7.1 is fixed, a user could point a conversation at another
organization's repository ID. This conflicts with the tenant-isolation
principle in Architecture §2.6 and API Design §39. Membership and
repository ownership should be verified (for example by calling the
API and Repository services, or by sharing the membership lookup).

## 7.3 Secrets in tracked files (medium)

- A local database password is written into `docker-compose.yml`, the
  default settings in the API and AI services, and `apractice.py`.
- `.env` files and `*.pem` are git-ignored, which is correct.
- The default `SECRET_KEY` value is a placeholder and must be set
  identically in the API, Repository, and AI services.

Move the database credentials to the ignored `.env` file and remove
`apractice.py` (a scratch script) from the repository.

## 7.4 CI covers only part of the system (medium)

- The workflow is still named "FlowForge CI".
- Backend tests run only for `Services/api`.
- Repository, Worker, and AI tests are not run.
- Docker images are built only for `api` and `frontend`, and the image
  tags use `flowforge/`.
- There are no lint steps for the Python services.

## 7.5 Smaller items

- Kafka events are dropped if publishing fails. A sync can stay
  `queued` indefinitely. An outbox or a retry would fix this.
- The Repository Service creates a new Kafka producer for each event.
- The worker's clone directory name uses `id(self)`.
- `repository_name` in the AI Service is set to the repository ID
  (marked TODO), so prompts do not contain the real name.
- The streaming endpoint is a GET with the message in the query string,
  and `EventSource` cannot send an `Authorization` header.
- Message history is rebuilt from all prior messages with no limit.
- Tables are created at startup in all four services with no
  migrations.
- `Repository.organization_id` and `GitHubInstallation.organization_id`
  have no foreign key to the API Service's table (intentional, but not
  enforced anywhere else).
- Test database files (`test_repo.db`, `test_temp.db`) are in the tree.
  Only `test_temp.db` is git-ignored.

---

# 8. Remaining Work (from the MVP boundary)

In suggested order:

1. Fix the Qdrant payload/filter contract (7.1) and add an AI Service
   integration test that retrieves a chunk written by the worker.
2. Add membership and repository-ownership checks to the AI Service
   (7.2).
3. Add the AI Service to `docker-compose.yml` and the Makefile.
4. Build the AI workspace in the frontend (conversation list, chat view,
   source references from retrieved chunks).
5. Decide the role model (6.1) and align code or docs.
6. Pull request ingestion, `pull_requests`, and the Code Review Agent.
7. Test Assistance.
8. CI coverage for all services (7.4).
9. Alembic migrations.
10. Observability, Redis (rate limiting and caching), Kubernetes, AWS.

---

# 9. Keeping This Document Current

When a feature moves from "not built" to "built", update sections 2, 4,
and 6 in the same change. When a known issue is fixed, remove it from
section 7 rather than marking it resolved, so the list stays short.
