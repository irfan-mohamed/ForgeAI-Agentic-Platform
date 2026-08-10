# ForgeAI — System Architecture

## 1. Purpose

This document defines the high-level technical architecture of ForgeAI.

It describes:

- Major system components
- Service boundaries
- Communication patterns
- Data storage responsibilities
- AI architecture
- Repository processing
- Event-driven workflows
- Observability
- Deployment architecture

The architecture is designed to be:

- Understandable
- Modular
- Scalable
- Observable
- Secure
- Suitable for incremental development

The initial implementation should avoid unnecessary complexity while preserving a path toward production-scale architecture.

---

# 2. Architecture Principles

ForgeAI follows these principles.

## 2.1 Product First

Technology must support a real product requirement.

A technology should not be introduced only because it is popular.

---

## 2.2 Modular Architecture

Each major responsibility should have a clear boundary.

Services should not contain unrelated business logic.

---

## 2.3 Asynchronous Processing

Long-running operations should not block user requests.

Examples:

- Repository synchronization
- Repository indexing
- Embedding generation
- AI code review
- Large repository analysis

These operations should run asynchronously.

---

## 2.4 Event-Driven Communication

Important state changes can generate events.

Examples:

- Repository connected
- Repository synchronized
- Pull request created
- Review completed
- Repository updated

Events allow independent components to react without tightly coupling them.

---

## 2.5 AI as a Capability

The AI system should be integrated into the platform rather than being the entire platform.

The application remains responsible for:

- Authentication
- Authorization
- Repository access
- Data management
- Workflow management
- Security
- Observability

AI components provide intelligence on top of these capabilities.

---

## 2.6 Tenant Isolation

ForgeAI is a multi-tenant platform.

Each organization's:

- Users
- Repositories
- Conversations
- Knowledge
- AI execution history

must remain isolated from other organizations.

---

# 3. High-Level Architecture

The platform consists of the following major layers.

    ┌───────────────────────────────────────────────┐
    │                  User Layer                   │
    │                                               │
    │              Web Application                 │
    └──────────────────────┬────────────────────────┘
                           │
                           ↓
    ┌───────────────────────────────────────────────┐
    │                Application Layer              │
    │                                               │
    │              API / Gateway                    │
    └──────────────────────┬────────────────────────┘
                           │
             ┌─────────────┼─────────────┐
             ↓             ↓             ↓
       Repository       AI Core       User/Auth
        Service         Service        Service
             │             │
             ↓             ↓
       Repository       AI Agents
       Processing       & Tools
             │             │
             └──────┬──────┘
                    ↓
    ┌───────────────────────────────────────────────┐
    │                 Data Layer                    │
    │                                               │
    │ PostgreSQL │ Redis │ Vector DB │ Object Store │
    └───────────────────────────────────────────────┘
                    │
                    ↓
    ┌───────────────────────────────────────────────┐
    │               Event Layer                     │
    │                                               │
    │                    Kafka                      │
    └───────────────────────────────────────────────┘
                    │
                    ↓
    ┌───────────────────────────────────────────────┐
    │             Observability Layer               │
    │                                               │
    │ OpenTelemetry │ Prometheus │ Grafana │ ELK    │
    └───────────────────────────────────────────────┘
                    │
                    ↓
    ┌───────────────────────────────────────────────┐
    │              Infrastructure                   │
    │                                               │
    │ Docker │ Kubernetes │ AWS │ CI/CD             │
    └───────────────────────────────────────────────┘

---

# 4. Frontend

The frontend is the primary interface for users.

It provides:

- Registration
- Login
- Organization management
- GitHub connection
- Repository management
- Repository status
- AI workspace
- Conversations
- Code review results
- Test assistance
- System status
- Observability information where appropriate

The frontend communicates with the application backend through APIs.

The frontend should not directly communicate with internal services.

---

# 5. API Gateway

The API Gateway provides the main entry point for frontend requests.

Conceptually:

    Frontend
        ↓
    API Gateway
        ↓
    Internal Services

Responsibilities include:

- Request routing
- Authentication verification
- Authorization checks
- Rate limiting
- Request validation
- Correlation/request identifiers

The gateway hides internal service topology from the frontend.

---

# 6. Core Services

The initial platform will use a small number of services.

The goal is to avoid creating a large number of microservices before they are necessary.

## 6.1 User / Organization Service

Responsible for:

- User accounts
- Authentication
- Organizations
- Organization membership
- Roles
- Permissions

Example:

    User
      ↓
    Organization
      ↓
    Members

---

## 6.2 Repository Service

Responsible for:

- GitHub integration
- GitHub App installation information
- Repository connections
- Repository metadata
- Repository synchronization requests
- Repository access state

It acts as the main boundary between ForgeAI and external source-control systems.

---

## 6.3 AI Service

Responsible for:

- AI conversations
- AI orchestration
- Agent execution
- Planning
- Tool selection
- AI responses
- AI execution history

The AI Service is the main intelligence layer.

---

## 6.4 Worker Service

Responsible for asynchronous and long-running work.

Examples:

- Repository synchronization
- File processing
- Indexing
- Embedding generation
- Code analysis
- AI review jobs

The worker consumes jobs/events and performs background processing.

---

# 7. Why We Are Not Creating Many Microservices Initially

The platform could eventually contain services such as:

- Code Review Service
- Security Service
- Architecture Service
- Testing Service
- Documentation Service
- DevOps Service
- Notification Service

However, these should not necessarily become separate services immediately.

Initially they can exist as modules within the AI Service or Worker Service.

Example:

    AI Service
    │
    ├── Engineering Agent
    ├── Code Review Agent
    └── Testing Agent

Later, if a component requires independent scaling or ownership, it can become a separate service.

This prevents the project from becoming unnecessarily complex.

---

# 8. AI Architecture

The user interacts primarily with one AI:

                User
                  ↓
            Engineering AI
                  │
        ┌─────────┼─────────┐
        ↓         ↓         ↓
    Code Review  Testing  Repository
       Agent      Agent   Intelligence

The Engineering AI determines what kind of assistance is required.

The specialized capabilities perform focused tasks.

The user does not need to understand which internal agent performed the work.

---

# 9. Repository Intelligence

Repository Intelligence is one of the most important components of ForgeAI.

Its purpose is to transform a repository into information that the AI can understand and retrieve.

Conceptual flow:

    GitHub Repository
           ↓
    Repository Synchronization
           ↓
    File Discovery
           ↓
    Source Processing
           ↓
    Document / Code Chunking
           ↓
    Embedding Generation
           ↓
    Vector Database
           ↓
    Repository Knowledge

The system should preserve enough information to identify where knowledge came from.

For example:

    Repository
        ↓
    File
        ↓
    Chunk
        ↓
    Repository Knowledge

This allows AI responses to reference relevant repository sources.

---

# 10. Retrieval-Augmented Generation

The AI workspace uses repository knowledge to answer questions.

Conceptual flow:

    User Question
          ↓
    Engineering AI
          ↓
    Repository Search
          ↓
    Relevant Knowledge
          ↓
    Context Construction
          ↓
    Language Model
          ↓
    AI Response

Example:

    User:

    "Where is authentication implemented?"

    ↓

    Search repository knowledge

    ↓

    Find relevant files

    ↓

    Provide context to AI

    ↓

    Generate answer

The AI should not rely solely on its general knowledge when answering repository-specific questions.

---

# 11. MCP and Tool Use

ForgeAI will eventually expose controlled capabilities to the AI through tools.

Examples:

    Repository Tools

    ├── Search repository
    ├── Read file
    ├── Get pull request
    ├── Get commit
    └── Get repository information

    Engineering Tools

    ├── Run tests
    ├── Analyze code
    └── Generate report

    GitHub Tools

    ├── Create issue
    ├── Add PR comment
    └── Get PR information

MCP can provide a standardized mechanism for exposing these capabilities to AI components.

The AI should only receive the tools it is authorized to use.

---

# 12. Kafka

Kafka provides the event backbone for asynchronous workflows.

Examples of events:

    repository.connected

    repository.sync.started

    repository.sync.completed

    repository.updated

    pull_request.created

    code_review.started

    code_review.completed

    test_generation.completed

These events allow independent components to react to system changes.

---

# 13. Repository Synchronization Flow

When a repository is connected:

    User
      ↓
    API Gateway
      ↓
    Repository Service
      ↓
    Create synchronization job
      ↓
    Kafka
      ↓
    Worker
      ↓
    GitHub
      ↓
    Repository files
      ↓
    Processing
      ↓
    Vector Database
      ↓
    PostgreSQL / Object Storage
      ↓
    repository.sync.completed

The user does not need to keep the browser open while synchronization takes place.

---

# 14. Pull Request Review Flow

A simplified review flow:

    Pull Request Created
           ↓
        GitHub
           ↓
      ForgeAI Event
           ↓
         Kafka
           ↓
        Worker
           ↓
    Engineering AI
           ↓
    Repository Retrieval
           ↓
    Code Review Agent
           ↓
    Testing Agent
           ↓
    Review Result
           ↓
    PostgreSQL
           ↓
    GitHub / ForgeAI UI

The review can eventually include:

- Code quality
- Bugs
- Security
- Architecture
- Testing gaps

---

# 15. PostgreSQL

PostgreSQL stores structured application data.

Examples:

    users
    organizations
    memberships
    repositories
    github_installations
    conversations
    messages
    agent_runs
    code_reviews
    review_findings
    jobs

PostgreSQL is the source of truth for application state.

---

# 16. Redis

Redis is used for short-lived and performance-sensitive information.

Initial uses:

- Response caching
- Repository query caching
- Rate limiting
- Temporary job state
- Session-related data where appropriate

Redis should not become the primary database.

---

# 17. Vector Database

The vector database stores semantic representations of repository knowledge.

Examples:

- Source code chunks
- Documentation chunks
- Architecture information
- Repository-related engineering knowledge

It is optimized for semantic retrieval.

It is not the source of truth for users, organizations, or repository metadata.

---

# 18. Object Storage

Object storage is used for larger files and generated artifacts.

Examples:

- Repository snapshots where required
- Generated reports
- Architecture diagrams
- Large analysis artifacts
- Future uploaded engineering documents

AWS S3 is the planned production object-storage provider.

---

# 19. Observability

ForgeAI must be observable.

The observability system contains three major categories.

## Metrics

Prometheus collects:

- Request count
- Request latency
- Error rate
- Worker jobs
- Kafka processing
- AI request metrics
- Repository indexing metrics

---

## Dashboards

Grafana visualizes:

- API health
- AI performance
- Repository processing
- Kafka activity
- Infrastructure health

---

## Logs

Application and service logs are collected centrally.

Elasticsearch stores searchable logs.

Kibana provides the interface for investigating them.

---

# 20. Distributed Tracing

OpenTelemetry provides distributed tracing.

Example:

    User Request
         ↓
    API Gateway
         ↓
    AI Service
         ↓
    Retrieval
         ↓
    Vector Database
         ↓
    AI Agent
         ↓
    Language Model
         ↓
    Response

A trace identifier allows developers to investigate the complete lifecycle of a request.

---

# 21. Docker

Each deployable component is containerized.

Initial containers may include:

    frontend
    api
    ai-service
    worker

Infrastructure dependencies may also run as containers during local development:

    PostgreSQL
    Redis
    Kafka
    Vector Database
    Elasticsearch
    Prometheus
    Grafana

Docker Compose can provide the initial local development environment.

---

# 22. Kubernetes

Kubernetes is used for production deployment.

Initial application workloads:

    frontend
    api
    ai-service
    worker

Infrastructure components may initially use managed services where appropriate.

Kubernetes is responsible for:

- Deployment
- Service discovery
- Health checks
- Restarting failed containers
- Scaling
- Configuration
- Secrets
- Rolling updates

---

# 23. AWS

AWS is the planned production environment.

The exact AWS service selection will be finalized during deployment design.

The initial architecture can include:

    AWS
     │
     ├── Kubernetes compute
     ├── Managed PostgreSQL
     ├── S3
     ├── Container Registry
     ├── Load Balancer
     └── Monitoring / infrastructure services

The project should avoid using AWS services unnecessarily.

---

# 24. CI/CD

GitHub Actions provides the initial CI/CD system.

Conceptual pipeline:

    Developer Push
          ↓
    GitHub Actions
          ↓
    Lint
          ↓
    Unit Tests
          ↓
    Integration Tests
          ↓
    Build Docker Image
          ↓
    Security Checks
          ↓
    Push Image
          ↓
    Deploy
          ↓
    Health Check

The pipeline should prevent deployment when important tests fail.

---

# 25. Security Boundaries

The architecture contains several security boundaries.

## User Boundary

Users can only access organizations they belong to.

## Organization Boundary

Organizations cannot access each other's data.

## Repository Boundary

AI tools can only access repositories authorized for the current organization.

## GitHub Boundary

ForgeAI can only access repositories permitted by the GitHub App installation.

## AI Tool Boundary

Agents can only use tools that they are authorized to use.

---

# 26. Initial Architecture

The first implementation should remain relatively small.

    ForgeAI
    │
    ├── Frontend
    │
    ├── API
    │
    ├── AI Service
    │
    ├── Worker
    │
    └── Infrastructure
         │
         ├── PostgreSQL
         ├── Redis
         ├── Kafka
         ├── Vector DB
         └── Observability

This architecture provides clear boundaries without creating unnecessary microservices.

---

# 27. Evolution of the Architecture

The architecture should evolve based on actual requirements.

### Stage 1

    API
    AI
    Worker

### Stage 2

Introduce:

    Kafka
    Redis
    Vector DB
    Observability

### Stage 3

Introduce:

    Kubernetes
    AWS
    CI/CD

### Stage 4

If required, split AI capabilities into independent services:

    Code Review Service
    Testing Service
    Security Service
    Architecture Service

The system should not start with the Stage 4 architecture.

---

# 28. Initial Architecture Goal

The objective is not to build the largest possible distributed system.

The objective is to build a system where:

1. A user can register.
2. A user can create an organization.
3. A user can connect GitHub.
4. A user can connect a private or public repository.
5. ForgeAI can synchronize the repository.
6. ForgeAI can build repository knowledge.
7. A user can ask repository-specific questions.
8. ForgeAI can perform an AI code review.
9. ForgeAI can assist with tests.
10. The system can process long-running tasks asynchronously.
11. The system is observable.
12. The system can be containerized and deployed.
13. The architecture can evolve without rewriting the entire application.

This is the first production-shaped version of ForgeAI.

---

# 29. Core Architecture Principle

ForgeAI should follow:

    Simple where possible.
    Distributed where necessary.
    Asynchronous where appropriate.
    AI-powered where intelligence is useful.
    Observable everywhere.
    Secure by default.