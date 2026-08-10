# ForgeAI — Service Design

## 1. Purpose

This document defines the responsibilities, boundaries, data ownership,
interfaces, and communication patterns of the core ForgeAI services.

The initial platform contains four primary application services:

1. User / Organization Service
2. Repository Service
3. AI Service
4. Worker Service

Additional capabilities such as code review, testing, security, and
architecture analysis initially exist as modules within the AI and Worker
services.

They are not independent microservices in the first version.

---

# 2. Service Architecture

The initial application architecture is:

    ┌─────────────────────────────────────────────┐
    │                  Frontend                   │
    └──────────────────────┬──────────────────────┘
                           │
                           ↓
    ┌─────────────────────────────────────────────┐
    │                 API Gateway                 │
    └─────────────┬─────────────┬─────────────────┘
                  │             │
                  ↓             ↓
        User / Organization   Repository
             Service           Service
                  │             │
                  │             ↓
                  │            Kafka
                  │             │
                  │             ↓
                  │           Worker
                  │             │
                  │             ↓
                  │        Repository Data
                  │             │
                  └──────┬──────┘
                         ↓
                     AI Service
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
        Engineering   Code Review  Testing
           Agent         Agent       Agent
              │
              ↓
        Repository Knowledge
              │
       ┌──────┼──────────────┐
       ↓      ↓              ↓
   PostgreSQL Redis      Vector DB


---

# 3. Service Boundary Principles

Each service should have a clear responsibility.

A service should:

- Own its business logic.
- Own the data it is responsible for.
- Expose a defined interface.
- Avoid directly modifying another service's database.
- Communicate through APIs or events.

A service should not exist simply because a technology makes it possible.

---

# 4. User / Organization Service

## Responsibility

The User / Organization Service manages ForgeAI users and organizations.

It is responsible for:

- User registration
- Login
- User identity
- Organizations
- Organization membership
- Roles
- Permissions
- Organization settings

---

## 4.1 Main Entities

### User

Represents a ForgeAI account.

Example information:

    User
    ├── id
    ├── name
    ├── email
    ├── password information
    └── created_at

---

### Organization

Represents a workspace.

Example:

    Organization
    ├── id
    ├── name
    ├── description
    └── created_at

---

### Membership

Connects users to organizations.

Example:

    Membership
    ├── user_id
    ├── organization_id
    └── role

Possible initial roles:

- Owner
- Member

More detailed roles can be added later.

---

## 4.2 APIs

Example endpoints:

    POST   /auth/register
    POST   /auth/login
    POST   /auth/logout

    GET    /users/me

    POST   /organizations
    GET    /organizations
    GET    /organizations/{organization_id}

    GET    /organizations/{organization_id}/members
    POST   /organizations/{organization_id}/members

The exact API contract will be defined in the API Design document.

---

## 4.3 Data Ownership

The User / Organization Service owns:

    users
    organizations
    memberships

Other services should not directly modify these tables.

---

# 5. Repository Service

## Responsibility

The Repository Service manages external source-code repositories.

Its main responsibilities are:

- GitHub integration
- GitHub App installation
- Repository connections
- Repository metadata
- Repository access state
- Repository synchronization requests
- Repository lifecycle

---

## 5.1 GitHub Integration

The Repository Service communicates with GitHub.

It manages information such as:

    GitHub Installation
        ↓
    GitHub Organization / Account
        ↓
    Repository
        ↓
    ForgeAI Organization

The service must respect the permissions granted by GitHub.

---

## 5.2 Main Entities

### GitHub Installation

Represents a GitHub App installation.

Example:

    GitHubInstallation
    ├── id
    ├── organization_id
    ├── github_installation_id
    └── status

---

### Repository

Represents a repository connected to ForgeAI.

Example:

    Repository
    ├── id
    ├── organization_id
    ├── github_repository_id
    ├── name
    ├── owner
    ├── visibility
    ├── default_branch
    └── status

Possible statuses:

    CONNECTING
    SYNCING
    INDEXING
    READY
    FAILED
    ACCESS_REVOKED

---

## 5.3 Repository Lifecycle

    GitHub Connected
           ↓
    Repository Selected
           ↓
    Repository Created
           ↓
    SYNCING
           ↓
    INDEXING
           ↓
    READY

If something fails:

    SYNCING
       ↓
    FAILED

If GitHub access is revoked:

    READY
       ↓
    ACCESS_REVOKED

---

## 5.4 APIs

Example endpoints:

    GET  /github/install
    GET  /github/callback

    GET  /organizations/{organization_id}/repositories/available

    POST /organizations/{organization_id}/repositories

    GET  /repositories/{repository_id}

    POST /repositories/{repository_id}/sync

    DELETE /repositories/{repository_id}

The exact GitHub OAuth/App flow will be specified separately.

---

## 5.5 Events Produced

The Repository Service can publish:

    repository.connected
    repository.sync.requested
    repository.disconnected
    repository.access.revoked
    repository.updated

---

## 5.6 Data Ownership

The Repository Service owns:

    github_installations
    repositories
    repository_connections
    repository_sync_state

It should not directly modify AI conversation or review data.

---

# 6. Worker Service

## Responsibility

The Worker Service performs long-running operations.

This is important because operations such as repository indexing should not make a user wait for a normal API request to finish.

---

# 6.1 Worker Responsibilities

Initial responsibilities include:

- Repository synchronization
- File processing
- Repository indexing
- Embedding generation
- Repository analysis
- Code review jobs
- Test generation jobs

---

# 6.2 Repository Processing

When the Repository Service publishes:

    repository.sync.requested

Kafka delivers the event to the Worker.

The Worker then:

    Receive Job
         ↓
    Access Repository
         ↓
    Discover Files
         ↓
    Filter Unnecessary Files
         ↓
    Process Relevant Files
         ↓
    Create Knowledge Chunks
         ↓
    Generate Embeddings
         ↓
    Store Knowledge
         ↓
    Mark Repository Ready

---

# 6.3 Worker Events

The Worker can publish:

    repository.sync.started
    repository.sync.completed
    repository.sync.failed

    repository.indexing.started
    repository.indexing.completed
    repository.indexing.failed

    code_review.started
    code_review.completed
    code_review.failed

---

# 6.4 Worker Scaling

Workers should be designed to process independent jobs.

For example:

    Repository A
        ↓
    Job A

    Repository B
        ↓
    Job B

    Repository C
        ↓
    Job C

These jobs can eventually be processed by multiple worker instances.

This provides a natural path toward horizontal scaling.

---

# 7. AI Service

## Responsibility

The AI Service is responsible for intelligent interaction with the user.

It manages:

- AI conversations
- Engineering AI
- Agent orchestration
- Repository-aware reasoning
- Tool selection
- AI execution
- AI responses

---

# 7.1 Engineering AI

The Engineering AI is the main AI interface.

The user interacts with:

    User
      ↓
    Engineering AI

The Engineering AI determines what information or capabilities are required.

Example:

    User:

    "Where is authentication implemented?"

    Engineering AI:

    1. Understand request
    2. Search repository knowledge
    3. Retrieve relevant files
    4. Construct context
    5. Ask language model
    6. Generate response

---

# 7.2 Specialized AI Modules

The initial AI Service contains:

    AI Service
    │
    ├── Engineering Agent
    │
    ├── Code Review Agent
    │
    └── Testing Agent

These are logical AI modules rather than independent microservices.

---

# 7.3 Engineering Agent

The Engineering Agent handles general repository assistance.

Examples:

    "Explain this repository."

    "Where is authentication?"

    "How does payment processing work?"

    "What files will be affected by this change?"

It can use repository search and other authorized tools.

---

# 7.4 Code Review Agent

The Code Review Agent analyzes code changes.

Possible analysis areas:

- Bugs
- Code quality
- Security
- Architecture
- Maintainability
- Testing gaps

Example:

    Pull Request
         ↓
    Retrieve changed code
         ↓
    Retrieve relevant repository context
         ↓
    Code Review Agent
         ↓
    Findings
         ↓
    Review Result

---

# 7.5 Testing Agent

The Testing Agent assists with testing.

Examples:

    Identify missing tests

    Identify edge cases

    Suggest test scenarios

    Generate test code

The initial system should allow developers to review generated tests
before applying them.

---

# 8. Repository Knowledge Layer

Repository knowledge is shared by the AI workflows.

The knowledge pipeline is:

    Repository
        ↓
    Files
        ↓
    Processing
        ↓
    Chunks
        ↓
    Embeddings
        ↓
    Vector Database

Metadata about the knowledge should identify:

    Organization
    Repository
    File
    Path
    Commit / Version
    Chunk

This allows knowledge to remain isolated and traceable.

---

# 9. AI Retrieval Flow

When the user asks:

    "How does authentication work?"

The AI Service performs:

    User Question
         ↓
    Engineering Agent
         ↓
    Repository Search
         ↓
    Relevant Knowledge
         ↓
    Context Construction
         ↓
    Language Model
         ↓
    Response

The AI response should preserve enough source information for the
user to understand where the answer came from.

---

# 10. MCP Tool Layer

AI agents should not receive unrestricted access to the system.

Instead, they use controlled tools.

Initial tools may include:

    Repository Tools

    search_repository
    read_file
    get_repository_structure
    get_pull_request
    get_commit

    Engineering Tools

    run_tests
    analyze_code

    GitHub Tools

    create_issue
    add_pr_comment

Each tool should have:

- Clear input
- Clear output
- Authorization checks
- Error handling

---

# 11. Service Communication

There are two primary communication patterns.

## Synchronous Communication

Used when the user needs an immediate response.

Example:

    Frontend
       ↓
    API
       ↓
    AI Service
       ↓
    Response

---

## Asynchronous Communication

Used for long-running operations.

Example:

    Repository Service
          ↓
        Kafka
          ↓
        Worker
          ↓
    Repository Processing

---

# 12. Kafka Topics

Initial topics can include:

    repository.events

    repository.sync

    repository.indexing

    pull_request.events

    ai.jobs

    code_review.jobs

The exact topic structure can evolve as the system grows.

---

# 13. Database Ownership

Each service conceptually owns its own data.

Initial ownership:

    User / Organization Service
        ↓
    users
    organizations
    memberships

    Repository Service
        ↓
    github_installations
    repositories
    repository_connections

    AI Service
        ↓
    conversations
    messages
    agent_runs
    code_reviews
    review_findings

    Worker
        ↓
    Processing state
    Job state

The Worker should not become a permanent owner of business data merely
because it processes it.

Where practical, long-term business data should belong to the service
responsible for that domain.

---

# 14. Shared Database vs Separate Databases

The initial project may use a single PostgreSQL deployment.

However, ownership boundaries should still be maintained logically.

Example:

    PostgreSQL
    │
    ├── users
    ├── organizations
    ├── memberships
    │
    ├── repositories
    ├── github_installations
    │
    ├── conversations
    ├── messages
    ├── agent_runs
    └── code_reviews

Services should access only the data they own through defined interfaces.

The architecture can later move toward separate databases when scaling
or organizational requirements justify it.

---

# 15. Redis Usage

Redis is shared infrastructure rather than a business-data owner.

Initial uses:

- Cache
- Rate limiting
- Temporary state
- Frequently requested repository information
- AI response caching where appropriate

Redis data should be treated as disposable.

The application should continue functioning correctly if cached data disappears.

---

# 16. Vector Database Ownership

The repository knowledge/indexing subsystem manages vector data.

The vector database contains:

    Repository
        ↓
    File
        ↓
    Chunk
        ↓
    Embedding

Vector data should always contain enough metadata to enforce:

    Organization isolation
    Repository isolation
    Source traceability

---

# 17. Object Storage Ownership

Object storage is used for large artifacts.

Potential artifacts include:

- Repository processing artifacts
- Code review reports
- Generated reports
- Architecture diagrams
- Future engineering documents

The database stores metadata and references rather than unnecessarily
storing large binary objects directly.

---

# 18. Error Handling

Every service must handle failures explicitly.

Examples:

### GitHub unavailable

    Repository Sync
        ↓
    GitHub Error
        ↓
    Retry
        ↓
    If repeated failure
        ↓
    Job marked FAILED

---

### AI Provider unavailable

    AI Request
        ↓
    Provider Error
        ↓
    Retry / fallback where appropriate
        ↓
    Inform user

---

### Vector Database unavailable

    Retrieval
        ↓
    Database Error
        ↓
    Request fails gracefully
        ↓
    Error recorded

The system should never silently return incorrect information because a
dependency failed.

---

# 19. Idempotency

Background operations should be designed so that repeating a job does
not corrupt the system.

Example:

    repository.sync.requested

may be delivered more than once.

The Worker should recognize whether the synchronization operation has
already been completed or is already running.

This is particularly important for event-driven processing.

---

# 20. Observability Responsibilities

Every service should provide:

- Structured logs
- Metrics
- Request identifiers
- Trace information
- Error information

Example:

    Request
       ↓
    trace_id = abc123

The same trace can be followed across:

    API
      ↓
    AI
      ↓
    Retrieval
      ↓
    Worker
      ↓
    Database

This makes production debugging possible.

---

# 21. Initial Service Repository Structure

ForgeAI will initially use a monorepo.

Conceptually:

    forgeai/
    │
    ├── frontend/
    │
    ├── services/
    │   │
    │   ├── api/
    │   │
    │   ├── ai/
    │   │
    │   ├── repository/
    │   │
    │   └── worker/
    │
    ├── infrastructure/
    │
    ├── docs/
    │
    ├── scripts/
    │
    ├── tests/
    │
    └── README.md

Each service is initially a folder rather than a separate repository.

---

# 22. Why a Monorepo

The initial project is developed by a small team / individual developer.

A monorepo provides:

- Simple development
- Shared documentation
- Easier local development
- Easier integration testing
- Easier version management
- Easier CI/CD

If ForgeAI eventually becomes a large organization with independent
engineering teams, services can be separated into repositories when
there is a genuine reason to do so.

---

# 23. Initial Development Boundaries

The first implementation should not build every service simultaneously.

Recommended order:

    1. User / Organization Service
            ↓
    2. Repository Service
            ↓
    3. Worker
            ↓
    4. Repository Knowledge
            ↓
    5. AI Service
            ↓
    6. Code Review
            ↓
    7. Testing Assistance
            ↓
    8. Observability
            ↓
    9. Docker
            ↓
    10. Kubernetes
            ↓
    11. AWS Deployment

---

# 24. Initial End-to-End Workflow

The first complete technical workflow should be:

    User
      ↓
    Frontend
      ↓
    API
      ↓
    User / Organization Service
      ↓
    Create Organization
      ↓
    Repository Service
      ↓
    GitHub
      ↓
    Repository Connected
      ↓
    Kafka
      ↓
    Worker
      ↓
    Repository Processing
      ↓
    Vector Database
      ↓
    Repository Ready
      ↓
    AI Service
      ↓
    Repository Retrieval
      ↓
    Language Model
      ↓
    AI Response
      ↓
    Frontend

This is the first vertical slice of ForgeAI.

---

# 25. Future Service Expansion

The following capabilities can eventually become independent services
if the system requires them:

    Code Review Service

    Security Service

    Testing Service

    Architecture Service

    Documentation Service

    DevOps Service

    Notification Service

    Analytics Service

They should initially remain modules where possible.

The decision to split a module into a service should be based on:

- Independent scaling requirements
- Independent deployment requirements
- Clear ownership
- High traffic
- Operational isolation
- Team ownership

Not simply because microservices are popular.

---

# 26. Service Design Principle

ForgeAI follows:

    Few services initially.

    Clear boundaries.

    Strong ownership.

    Async processing for expensive work.

    Events for decoupled workflows.

    APIs for direct interactions.

    AI agents as modules.

    Services only when justified.

This allows the project to remain understandable while still
demonstrating production-oriented architecture.