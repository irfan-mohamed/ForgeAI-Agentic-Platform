# ForgeAI — Data Model

## 1. Purpose

This document defines the conceptual data model for ForgeAI.

It describes:

- Core entities
- Relationships between entities
- Data ownership
- Organization isolation
- Repository information
- AI conversation data
- Agent execution data
- Code review data
- Repository knowledge metadata
- Job and processing state

This document defines the logical model.

The physical PostgreSQL schema, indexes, constraints, and migrations will
be designed during implementation.

---

# 2. Data Model Principles

ForgeAI follows these principles:

1. Every organization must be isolated from other organizations.
2. Every repository belongs to an organization.
3. Repository knowledge must be traceable to its source repository.
4. AI conversations must belong to an organization.
5. AI execution must be traceable.
6. Background jobs must have explicit states.
7. Large files and artifacts should not unnecessarily be stored in PostgreSQL.
8. Vector data must contain enough metadata to enforce organization and
   repository isolation.
9. Services should respect data ownership defined in the Service Design.
10. The database should store application state, not transient cache data.

---

# 3. High-Level Entity Relationship

The core relationship is:

    User
      │
      │
      ↓
    Membership
      │
      ↓
    Organization
      │
      ├───────────────┐
      ↓               ↓
    Repository      Conversations
      │               │
      │               ↓
      │            Messages
      │
      ├───────────────┐
      ↓               ↓
    Repository       Pull Requests
    Knowledge          │
                       ↓
                  Code Reviews
                       │
                       ↓
                Review Findings


Additional relationships:

    Organization
        ↓
    GitHub Installation
        ↓
    GitHub Repositories

    Conversation
        ↓
    Agent Runs
        ↓
    Tool Calls

    Repository
        ↓
    Processing Jobs
        ↓
    Processing Runs

---

# 4. User

The User entity represents a ForgeAI account.

## Purpose

Stores the identity of a person using ForgeAI.

## Important fields

    User
    ├── id
    ├── name
    ├── email
    ├── password_hash
    ├── status
    ├── created_at
    └── updated_at

## Notes

The password itself must never be stored.

Only a secure password hash is stored.

The user's email should be unique.

---

# 5. Organization

An Organization represents a ForgeAI workspace.

Examples:

    Personal Projects

    Acme Engineering

    FlowForge

An organization owns the engineering resources connected to ForgeAI.

## Important fields

    Organization
    ├── id
    ├── name
    ├── slug
    ├── description
    ├── status
    ├── created_at
    └── updated_at

---

# 6. Membership

A user can belong to multiple organizations.

Therefore User and Organization have a many-to-many relationship.

Membership represents that relationship.

    User
      │
      ├──── Membership ──── Organization
      │
      └──── Membership ──── Organization

## Important fields

    Membership
    ├── id
    ├── user_id
    ├── organization_id
    ├── role
    ├── status
    ├── created_at
    └── updated_at

## Initial roles

The first version supports:

    OWNER
    MEMBER

Additional roles can be introduced later.

---

# 7. GitHub Installation

A GitHub Installation represents the connection between a ForgeAI
organization and a GitHub App installation.

## Purpose

It allows ForgeAI to know which GitHub account or organization granted
the application access.

## Important fields

    GitHubInstallation
    ├── id
    ├── organization_id
    ├── github_installation_id
    ├── github_account_id
    ├── github_account_login
    ├── account_type
    ├── status
    ├── installed_at
    └── updated_at

The GitHub installation belongs to a ForgeAI organization.

---

# 8. Repository

Repository represents a GitHub repository connected to ForgeAI.

## Important fields

    Repository
    ├── id
    ├── organization_id
    ├── github_installation_id
    ├── github_repository_id
    ├── name
    ├── full_name
    ├── owner
    ├── description
    ├── visibility
    ├── default_branch
    ├── status
    ├── last_synced_at
    ├── created_at
    └── updated_at

## Repository Status

Possible states:

    CONNECTING
    SYNCING
    INDEXING
    READY
    FAILED
    ACCESS_REVOKED
    DISCONNECTED

---

# 9. Repository Relationship

The relationship is:

    Organization
          │
          │ owns
          ↓
      Repository
          │
          │ connected through
          ↓
    GitHub Installation

A repository must belong to exactly one ForgeAI organization.

This is critical for tenant isolation.

---

# 10. Repository Synchronization

A repository may be synchronized many times.

For example:

    Initial synchronization
          ↓
    Commit update
          ↓
    Pull request update
          ↓
    Another commit
          ↓
    Another synchronization

Therefore synchronization should not be represented only by a field on
the Repository entity.

We maintain synchronization history.

## Repository Sync

    RepositorySync
    ├── id
    ├── repository_id
    ├── status
    ├── commit_sha
    ├── started_at
    ├── completed_at
    ├── files_processed
    ├── files_failed
    ├── error_message
    └── created_at

Possible statuses:

    QUEUED
    RUNNING
    COMPLETED
    FAILED
    CANCELLED

---

# 11. Repository Knowledge

Repository Knowledge represents information derived from repository
files.

The knowledge itself may be stored in a vector database.

PostgreSQL stores the metadata required to identify and manage that
knowledge.

## Important fields

    RepositoryKnowledge
    ├── id
    ├── repository_id
    ├── file_path
    ├── commit_sha
    ├── chunk_identifier
    ├── content_type
    ├── language
    ├── vector_reference
    ├── created_at
    └── updated_at

The actual vector is stored in the vector database.

---

# 12. Knowledge Source Relationship

Knowledge must always be traceable.

    Organization
         ↓
    Repository
         ↓
    File
         ↓
    Chunk
         ↓
    Vector

This allows ForgeAI to answer:

> "Where did this information come from?"

For example:

    Repository:
    payment-service

    File:
    src/payment/service.py

    Chunk:
    payment-processing-function

---

# 13. Repository File Metadata

The platform may maintain metadata about files discovered during
repository processing.

## Repository File

    RepositoryFile
    ├── id
    ├── repository_id
    ├── path
    ├── file_type
    ├── language
    ├── size
    ├── checksum
    ├── commit_sha
    ├── is_indexed
    ├── created_at
    └── updated_at

This helps determine which files changed during future synchronization.

---

# 14. Conversation

Conversation represents an AI interaction within an organization.

A conversation may optionally be associated with a repository.

## Important fields

    Conversation
    ├── id
    ├── organization_id
    ├── repository_id
    ├── user_id
    ├── title
    ├── status
    ├── created_at
    └── updated_at

Example:

    Conversation
    "How does authentication work?"

    Organization:
    Acme Engineering

    Repository:
    backend

    User:
    Irfan

---

# 15. Message

A conversation contains multiple messages.

    Conversation
        │
        ├── Message
        ├── Message
        ├── Message
        └── Message

## Important fields

    Message
    ├── id
    ├── conversation_id
    ├── role
    ├── content
    ├── sequence_number
    ├── created_at
    └── metadata

Possible roles:

    USER
    ASSISTANT
    SYSTEM
    TOOL

The initial implementation should keep message structure simple.

---

# 16. Agent Run

An Agent Run represents one execution of an AI workflow.

For example:

    User:
    "Review this pull request."

This may produce:

    Agent Run
        ↓
    Engineering Agent
        ↓
    Repository Retrieval
        ↓
    Code Review Agent
        ↓
    Testing Agent
        ↓
    Final Response

The entire execution should be traceable.

## Important fields

    AgentRun
    ├── id
    ├── organization_id
    ├── repository_id
    ├── conversation_id
    ├── user_id
    ├── agent_type
    ├── status
    ├── started_at
    ├── completed_at
    ├── input_reference
    ├── output_reference
    ├── error_message
    └── created_at

Possible statuses:

    QUEUED
    RUNNING
    COMPLETED
    FAILED
    CANCELLED

---

# 17. Tool Call

An agent may use tools.

For example:

    Engineering Agent
          ↓
    search_repository()
          ↓
    read_file()
          ↓
    get_pull_request()

Each tool execution should be traceable.

## Important fields

    ToolCall
    ├── id
    ├── agent_run_id
    ├── tool_name
    ├── input
    ├── output
    ├── status
    ├── started_at
    ├── completed_at
    └── error_message

Sensitive values should not be stored unnecessarily in tool inputs or
outputs.

---

# 18. Pull Request

A Pull Request represents a GitHub pull request associated with a
connected ForgeAI repository.

## Important fields

    PullRequest
    ├── id
    ├── repository_id
    ├── github_pr_id
    ├── number
    ├── title
    ├── description
    ├── author
    ├── source_branch
    ├── target_branch
    ├── status
    ├── created_at
    └── updated_at

Possible statuses:

    OPEN
    CLOSED
    MERGED

---

# 19. Code Review

A Code Review represents a ForgeAI analysis of a Pull Request.

One Pull Request may have multiple ForgeAI reviews.

For example:

    Pull Request #42

        ↓

    Review #1

        ↓

    Developer changes code

        ↓

    Review #2

Therefore:

    PullRequest
         │
         ├── CodeReview
         ├── CodeReview
         └── CodeReview

## Important fields

    CodeReview
    ├── id
    ├── pull_request_id
    ├── repository_id
    ├── agent_run_id
    ├── status
    ├── overall_score
    ├── summary
    ├── started_at
    ├── completed_at
    └── created_at

---

# 20. Review Finding

A Code Review contains individual findings.

Example:

    Code Review
        │
        ├── Finding
        ├── Finding
        ├── Finding
        └── Finding

## Important fields

    ReviewFinding
    ├── id
    ├── code_review_id
    ├── category
    ├── severity
    ├── title
    ├── description
    ├── file_path
    ├── line_start
    ├── line_end
    ├── recommendation
    └── created_at

Possible categories:

    CODE_QUALITY
    BUG
    SECURITY
    ARCHITECTURE
    PERFORMANCE
    TESTING

Possible severity:

    CRITICAL
    HIGH
    MEDIUM
    LOW
    INFO

---

# 21. Processing Job

Long-running operations need explicit job state.

Examples:

    Repository Sync

    Repository Indexing

    Code Review

    Test Generation

## Important fields

    Job
    ├── id
    ├── organization_id
    ├── repository_id
    ├── job_type
    ├── status
    ├── attempts
    ├── started_at
    ├── completed_at
    ├── error_message
    └── created_at

Possible job types:

    REPOSITORY_SYNC
    REPOSITORY_INDEX
    CODE_REVIEW
    TEST_GENERATION

Possible statuses:

    QUEUED
    RUNNING
    COMPLETED
    FAILED
    CANCELLED

---

# 22. Organization Isolation

Organization is the primary tenant boundary.

Conceptually:

    Organization A
        │
        ├── Users
        ├── Repositories
        ├── Conversations
        ├── Agent Runs
        └── Reviews


    Organization B
        │
        ├── Users
        ├── Repositories
        ├── Conversations
        ├── Agent Runs
        └── Reviews

Data from Organization A must never be returned to Organization B.

---

# 23. Tenant Identification

Most organization-owned entities should contain:

    organization_id

This allows the application to enforce tenant isolation.

For example:

    Repository
    ├── id
    ├── organization_id
    └── ...

    Conversation
    ├── id
    ├── organization_id
    └── ...

    AgentRun
    ├── id
    ├── organization_id
    └── ...

Even when an organization relationship can be inferred through another
entity, explicit tenant information may be retained where it improves
security, querying, or auditing.

---

# 24. Core Relationship Diagram

The primary data relationships are:

    USER
      │
      │ many-to-many
      ↓
    MEMBERSHIP
      │
      ↓
    ORGANIZATION
      │
      ├───────────────┐
      │               │
      ↓               ↓
    GITHUB         REPOSITORY
    INSTALLATION      │
                      ├──────────────┐
                      ↓              ↓
                REPOSITORY       PULL REQUEST
                  FILES              │
                      │              ↓
                      ↓         CODE REVIEW
                REPOSITORY            │
                 KNOWLEDGE            ↓
                                REVIEW FINDING


    ORGANIZATION
         │
         ↓
    CONVERSATION
         │
         ├── MESSAGE
         │
         └── AGENT RUN
                 │
                 └── TOOL CALL


    REPOSITORY
         │
         ↓
       JOB
         │
         ↓
      WORKER

---

# 25. Data Storage Responsibilities

Different storage systems have different responsibilities.

## PostgreSQL

Stores structured application state:

- Users
- Organizations
- Memberships
- GitHub installations
- Repositories
- Conversations
- Messages
- Agent runs
- Tool calls
- Pull requests
- Code reviews
- Findings
- Jobs
- Repository metadata

---

## Redis

Stores temporary or cached information:

- Cache
- Rate limits
- Temporary state
- Short-lived job information

Redis is not the source of truth.

---

## Vector Database

Stores semantic repository knowledge:

- Code chunks
- Documentation chunks
- Embedded engineering knowledge

---

## Object Storage

Stores large artifacts:

- Reports
- Diagrams
- Large processing artifacts
- Future uploaded documents

---

# 26. Data Retention Considerations

The following categories may require different retention policies:

### Account Data

Retained while the user account exists.

### Repository Metadata

Retained while the repository remains connected.

### Repository Knowledge

Can be rebuilt from the source repository and may therefore have a
different retention policy.

### Conversations

May be retained according to organization settings.

### AI Execution History

May be retained for debugging, auditing, evaluation, and observability.

### Logs

Should have a shorter retention period than core business data.

Exact retention policies will be defined later.

---

# 27. Versioning and Repository Knowledge

Repository knowledge changes when the repository changes.

Example:

    Commit A
       ↓
    Repository Knowledge A

    Commit B
       ↓
    Repository Knowledge B

The system should retain enough source/version metadata to understand
which repository state produced a piece of knowledge.

This helps prevent the AI from answering a question using outdated
information.

---

# 28. Data Integrity

Important relationships must have appropriate constraints.

Examples:

- User email should be unique.
- Organization slug should be unique.
- Membership should be unique for a user/organization pair.
- Repository should not be duplicated within an organization.
- Pull request number should be unique within a repository.
- Review findings must belong to an existing code review.
- Agent tool calls must belong to an existing agent run.

Exact database constraints will be implemented during schema design.

---

# 29. Data Flow Example

A repository is connected.

    Organization
         ↓
    Repository
         ↓
    Repository Sync
         ↓
    Repository Files
         ↓
    Repository Knowledge
         ↓
    Vector Database

A user asks a question.

    User
      ↓
    Conversation
      ↓
    Message
      ↓
    Agent Run
      ↓
    Repository Retrieval
      ↓
    Language Model
      ↓
    Assistant Message

A Pull Request is reviewed.

    Pull Request
         ↓
    Job
         ↓
    Agent Run
         ↓
    Code Review
         ↓
    Review Findings

---

# 30. Initial Data Model Scope

The first implementation should focus on these entities:

    User
    Organization
    Membership

    GitHubInstallation
    Repository
    RepositorySync

    RepositoryFile
    RepositoryKnowledge

    Conversation
    Message

    AgentRun
    ToolCall

    PullRequest
    CodeReview
    ReviewFinding

    Job

Additional entities should only be introduced when the product requires
them.

---

# 31. Data Model Principle

The goal of the data model is not to predict every possible future
feature.

The goal is to provide a clean foundation for the current product while
allowing the system to evolve.

The most important relationships are:

    User
      ↓
    Organization
      ↓
    Repository
      ↓
    Repository Knowledge
      ↓
    AI

and:

    Repository
      ↓
    Pull Request
      ↓
    Code Review
      ↓
    Findings

and:

    Conversation
      ↓
    Agent Run
      ↓
    Tool Calls

These relationships form the core data model of ForgeAI.