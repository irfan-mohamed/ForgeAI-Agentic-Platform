# ForgeAI — API Design

## 1. Purpose

This document defines the initial API contract for ForgeAI.

It describes:

- API structure
- Authentication
- Organization management
- GitHub integration
- Repository management
- Repository synchronization
- AI conversations
- Agent execution
- Code reviews
- Jobs
- Error handling
- Authorization

The API is designed around REST principles for the initial version.

Internal asynchronous workflows may use events rather than HTTP.

---

# 2. API Architecture

The frontend communicates with ForgeAI through the API layer.

    Frontend
        │
        ↓
    API Gateway
        │
        ├── User / Organization
        ├── Repository
        ├── AI
        └── Code Review
                │
                ↓
              Kafka
                │
                ↓
              Worker

The frontend should not directly communicate with:

- PostgreSQL
- Redis
- Kafka
- Vector Database
- Internal workers

---

# 3. Base URL

Development:

    http://localhost:<port>/api/v1

Production:

    https://api.forgeai.example/api/v1

The actual production domain will be decided during deployment.

All public API endpoints should be versioned.

Example:

    /api/v1/auth/register

This allows future versions to be introduced without immediately
breaking existing clients.

---

# 4. API Conventions

## HTTP Methods

Use standard HTTP methods:

    GET       Retrieve data
    POST      Create or trigger an action
    PATCH     Partially update data
    DELETE    Remove or disconnect data

---

# 5. Authentication

Authentication endpoints do not require an authenticated user.

## Register

    POST /auth/register

### Request

    {
      "name": "Irfan",
      "email": "irfan@example.com",
      "password": "..."
    }

### Response

    {
      "user": {
        "id": "...",
        "name": "Irfan",
        "email": "irfan@example.com"
      }
    }

The response must not contain the user's password.

---

# 6. Login

    POST /auth/login

### Request

    {
      "email": "irfan@example.com",
      "password": "..."
    }

### Response

    {
      "user": {
        "id": "...",
        "name": "Irfan",
        "email": "..."
      }
    }

Authentication/session behavior will be finalized during security
implementation.

The API must not expose sensitive authentication information.

---

# 7. Current User

    GET /users/me

Requires authentication.

### Response

    {
      "id": "...",
      "name": "Irfan",
      "email": "...",
      "organizations": [
        {
          "id": "...",
          "name": "Acme Engineering",
          "role": "OWNER"
        }
      ]
    }

---

# 8. Logout

    POST /auth/logout

Requires authentication.

The endpoint invalidates the user's current authenticated session.

---

# 9. Organizations

## Create Organization

    POST /organizations

### Request

    {
      "name": "Acme Engineering",
      "description": "Engineering workspace"
    }

### Response

    {
      "id": "...",
      "name": "Acme Engineering",
      "description": "Engineering workspace",
      "role": "OWNER"
    }

The authenticated user becomes the initial owner.

---

# 10. List Organizations

    GET /organizations

Returns organizations that the authenticated user belongs to.

### Response

    {
      "organizations": [
        {
          "id": "...",
          "name": "Acme Engineering",
          "role": "OWNER"
        },
        {
          "id": "...",
          "name": "Personal Projects",
          "role": "MEMBER"
        }
      ]
    }

---

# 11. Get Organization

    GET /organizations/{organization_id}

Requires membership in the organization.

### Response

    {
      "id": "...",
      "name": "Acme Engineering",
      "description": "...",
      "created_at": "..."
    }

---

# 12. Organization Members

## List Members

    GET /organizations/{organization_id}/members

### Response

    {
      "members": [
        {
          "user_id": "...",
          "name": "Irfan",
          "email": "...",
          "role": "OWNER"
        }
      ]
    }

---

## Add Member

    POST /organizations/{organization_id}/members

### Request

    {
      "email": "developer@example.com",
      "role": "MEMBER"
    }

The detailed invitation system may be implemented later.

---

# 13. GitHub Integration

GitHub integration is performed through the ForgeAI GitHub App.

The frontend should not receive or manage GitHub installation credentials
directly.

---

# 14. Start GitHub Installation

    GET /organizations/{organization_id}/github/install

Requires appropriate organization permissions.

The API returns or redirects the user to the GitHub App installation
flow.

Conceptual flow:

    ForgeAI
       ↓
    GitHub Installation
       ↓
    User authorizes App
       ↓
    GitHub
       ↓
    ForgeAI callback

---

# 15. GitHub Installation Callback

    GET /github/callback

The callback completes the GitHub installation process.

The Repository Service records the GitHub installation associated with
the ForgeAI organization.

The exact callback parameters depend on the GitHub App integration.

---

# 16. Get GitHub Connection Status

    GET /organizations/{organization_id}/github

### Response

    {
      "connected": true,
      "account": {
        "login": "acme",
        "type": "Organization"
      }
    }

If the organization has no active GitHub connection:

    {
      "connected": false
    }

---

# 17. List Available Repositories

    GET /organizations/{organization_id}/github/repositories

This returns repositories available to ForgeAI through the GitHub App
installation.

### Response

    {
      "repositories": [
        {
          "github_repository_id": "...",
          "name": "backend",
          "full_name": "acme/backend",
          "visibility": "private",
          "default_branch": "main"
        },
        {
          "github_repository_id": "...",
          "name": "frontend",
          "full_name": "acme/frontend",
          "visibility": "private",
          "default_branch": "main"
        }
      ]
    }

ForgeAI must only return repositories that GitHub has authorized the
installation to access.

---

# 18. Connect Repository

    POST /organizations/{organization_id}/repositories

### Request

    {
      "github_repository_id": "123456"
    }

### Response

    {
      "id": "...",
      "name": "backend",
      "full_name": "acme/backend",
      "status": "CONNECTING"
    }

The repository is now connected to the ForgeAI organization.

A synchronization job is created asynchronously.

---

# 19. List Connected Repositories

    GET /organizations/{organization_id}/repositories

### Response

    {
      "repositories": [
        {
          "id": "...",
          "name": "backend",
          "visibility": "private",
          "status": "READY",
          "last_synced_at": "..."
        }
      ]
    }

---

# 20. Get Repository

    GET /repositories/{repository_id}

### Response

    {
      "id": "...",
      "name": "backend",
      "full_name": "acme/backend",
      "visibility": "private",
      "default_branch": "main",
      "status": "READY",
      "last_synced_at": "..."
    }

The API must verify that the authenticated user has access to the
repository through organization membership.

---

# 21. Synchronize Repository

    POST /repositories/{repository_id}/sync

This requests a new synchronization.

### Response

    {
      "job_id": "...",
      "repository_id": "...",
      "status": "QUEUED"
    }

The API should return quickly.

The actual synchronization is performed asynchronously.

---

# 22. Repository Synchronization Status

    GET /repositories/{repository_id}/sync/status

### Response

    {
      "status": "INDEXING",
      "progress": {
        "files_discovered": 1240,
        "files_processed": 830,
        "files_failed": 2
      }
    }

Possible repository states:

    CONNECTING
    SYNCING
    INDEXING
    READY
    FAILED
    ACCESS_REVOKED
    DISCONNECTED

---

# 23. Disconnect Repository

    DELETE /repositories/{repository_id}

The repository is disconnected from ForgeAI.

The exact retention/deletion behavior for repository knowledge is
controlled by the platform's data retention policy.

---

# 24. AI Conversations

## Create Conversation

    POST /organizations/{organization_id}/conversations

### Request

    {
      "repository_id": "...",
      "title": "Payment Service Investigation"
    }

### Response

    {
      "id": "...",
      "repository_id": "...",
      "title": "Payment Service Investigation"
    }

The repository association may be optional for future organization-wide
conversations.

---

# 25. List Conversations

    GET /organizations/{organization_id}/conversations

Optional query parameters:

    ?repository_id=...
    ?page=1
    ?limit=20

### Response

    {
      "conversations": [
        {
          "id": "...",
          "title": "Payment Service Investigation",
          "repository_id": "...",
          "updated_at": "..."
        }
      ]
    }

---

# 26. Get Conversation

    GET /conversations/{conversation_id}

### Response

    {
      "id": "...",
      "title": "Payment Service Investigation",
      "repository_id": "...",
      "messages": [
        {
          "id": "...",
          "role": "USER",
          "content": "How does authentication work?"
        },
        {
          "id": "...",
          "role": "ASSISTANT",
          "content": "Authentication is handled by..."
        }
      ]
    }

---

# 27. Send AI Message

    POST /conversations/{conversation_id}/messages

### Request

    {
      "content": "How does authentication work?"
    }

### Response

    {
      "message_id": "...",
      "agent_run_id": "...",
      "status": "COMPLETED",
      "content": "Authentication is handled by..."
    }

The AI Service performs repository retrieval and reasoning before
returning the response.

---

# 28. AI Message Processing

Conceptually:

    POST /conversations/{id}/messages
                    ↓
             Create User Message
                    ↓
             Start Agent Run
                    ↓
             Engineering Agent
                    ↓
             Repository Retrieval
                    ↓
             Context Construction
                    ↓
             Language Model
                    ↓
             Assistant Message
                    ↓
             Return Response

For longer-running operations, the API may return a queued response
instead of waiting for completion.

---

# 29. Agent Run

## Get Agent Run

    GET /agent-runs/{agent_run_id}

### Response

    {
      "id": "...",
      "type": "ENGINEERING",
      "status": "COMPLETED",
      "started_at": "...",
      "completed_at": "..."
    }

This endpoint allows the frontend to inspect the state of an AI
operation.

---

# 30. Pull Requests

## List Pull Requests

    GET /repositories/{repository_id}/pull-requests

Optional:

    ?status=open
    ?page=1
    ?limit=20

### Response

    {
      "pull_requests": [
        {
          "id": "...",
          "number": 42,
          "title": "Add payment retry logic",
          "status": "OPEN",
          "author": "developer"
        }
      ]
    }

---

# 31. Get Pull Request

    GET /pull-requests/{pull_request_id}

### Response

    {
      "id": "...",
      "number": 42,
      "title": "Add payment retry logic",
      "status": "OPEN",
      "repository_id": "..."
    }

---

# 32. Start Code Review

    POST /pull-requests/{pull_request_id}/reviews

### Response

    {
      "review_id": "...",
      "job_id": "...",
      "status": "QUEUED"
    }

Code review is asynchronous because it may involve:

- Repository retrieval
- Code analysis
- Multiple AI agents
- Test analysis
- Large language model calls

---

# 33. Get Code Review

    GET /code-reviews/{review_id}

### Response

    {
      "id": "...",
      "pull_request_id": "...",
      "status": "COMPLETED",
      "overall_score": 7.8,
      "summary": "The change is generally sound...",
      "findings": [
        {
          "id": "...",
          "category": "TESTING",
          "severity": "MEDIUM",
          "title": "Missing failure-path test",
          "file_path": "src/payment/service.py",
          "line_start": 82,
          "line_end": 95,
          "recommendation": "Add a test for..."
        }
      ]
    }

---

# 34. Jobs

Long-running operations create jobs.

## Get Job

    GET /jobs/{job_id}

### Response

    {
      "id": "...",
      "type": "REPOSITORY_SYNC",
      "status": "RUNNING",
      "progress": 65
    }

Possible statuses:

    QUEUED
    RUNNING
    COMPLETED
    FAILED
    CANCELLED

---

# 35. API and Kafka Relationship

Not every operation should directly call another service.

Example:

    POST /repositories/{id}/sync
              ↓
        Repository API
              ↓
        Create Job
              ↓
           Kafka
              ↓
          Worker
              ↓
      Repository Processing

The API request finishes quickly.

The long-running operation happens in the background.

---

# 36. Repository Update Event

When GitHub reports a repository update:

    GitHub
       ↓
    Webhook
       ↓
    Repository Service
       ↓
    Publish Event
       ↓
    Kafka
       ↓
    Worker
       ↓
    Process Changed Files
       ↓
    Update Repository Knowledge

The frontend does not need to be involved in the processing pipeline.

---

# 37. GitHub Webhooks

ForgeAI will eventually receive GitHub events such as:

    push
    pull_request
    installation
    installation_repositories

These events allow ForgeAI to react to repository changes.

Example:

    GitHub Push
         ↓
    ForgeAI Webhook
         ↓
    Validate Event
         ↓
    Identify Repository
         ↓
    Publish Event
         ↓
    Kafka
         ↓
    Worker

---

# 38. Authorization

Authentication answers:

> Who are you?

Authorization answers:

> Are you allowed to perform this operation?

Every organization-scoped endpoint must verify:

    Authenticated User
            ↓
    Organization Membership
            ↓
    Required Role / Permission
            ↓
    Resource Ownership
            ↓
    Allow / Deny

---

# 39. Example Authorization

User A belongs to:

    Organization A

Repository A belongs to:

    Organization A

Therefore:

    User A → Repository A
    ALLOWED

If:

    User A → Organization A
    Repository B → Organization B

Then:

    User A → Repository B
    DENIED

The API must never rely only on an ID supplied by the client.

---

# 40. Error Response Format

API errors should use a consistent format.

Example:

    {
      "error": {
        "code": "REPOSITORY_NOT_FOUND",
        "message": "The requested repository could not be found.",
        "request_id": "..."
      }
    }

---

# 41. Common Error Codes

Initial error categories:

    INVALID_REQUEST
    UNAUTHORIZED
    FORBIDDEN
    NOT_FOUND

    ORGANIZATION_NOT_FOUND
    REPOSITORY_NOT_FOUND
    REPOSITORY_ACCESS_DENIED

    GITHUB_NOT_CONNECTED
    GITHUB_ACCESS_REVOKED

    REPOSITORY_SYNC_FAILED
    AI_REQUEST_FAILED
    AI_PROVIDER_UNAVAILABLE

    JOB_NOT_FOUND
    JOB_FAILED

---

# 42. HTTP Status Codes

Use standard HTTP status codes.

    200 OK
    201 CREATED
    202 ACCEPTED
    204 NO CONTENT

    400 BAD REQUEST
    401 UNAUTHORIZED
    403 FORBIDDEN
    404 NOT FOUND
    409 CONFLICT
    422 UNPROCESSABLE ENTITY
    429 TOO MANY REQUESTS
    500 INTERNAL SERVER ERROR
    502 BAD GATEWAY
    503 SERVICE UNAVAILABLE

---

# 43. Request IDs

Every API request should receive a request identifier.

Example:

    X-Request-ID: abc123

The identifier should appear in:

- API logs
- Error responses
- Relevant traces
- Background job records

This allows a developer to trace a user request through the system.

---

# 44. Pagination

List endpoints should support pagination.

Example:

    GET /organizations/{id}/repositories?page=1&limit=20

The response may include:

    {
      "items": [],
      "page": 1,
      "limit": 20,
      "total": 100
    }

Cursor-based pagination may be introduced later for very large datasets.

---

# 45. API Security

The API must:

- Validate all input
- Authenticate protected requests
- Authorize organization access
- Validate repository ownership
- Rate-limit sensitive operations
- Avoid returning secrets
- Avoid exposing internal errors
- Log security-relevant events

GitHub credentials or installation secrets must never be returned to
the frontend.

---

# 46. Initial API Surface

The first implementation should focus on:

## Authentication

    POST /auth/register
    POST /auth/login
    POST /auth/logout
    GET  /users/me

## Organizations

    POST /organizations
    GET  /organizations
    GET  /organizations/{id}

## GitHub

    GET /organizations/{id}/github/install
    GET /github/callback
    GET /organizations/{id}/github
    GET /organizations/{id}/github/repositories

## Repositories

    POST   /organizations/{id}/repositories
    GET    /organizations/{id}/repositories
    GET    /repositories/{id}
    POST   /repositories/{id}/sync
    GET    /repositories/{id}/sync/status
    DELETE /repositories/{id}

## AI

    POST /organizations/{id}/conversations
    GET  /organizations/{id}/conversations
    GET  /conversations/{id}
    POST /conversations/{id}/messages
    GET  /agent-runs/{id}

## Code Review

    GET  /repositories/{id}/pull-requests
    GET  /pull-requests/{id}
    POST /pull-requests/{id}/reviews
    GET  /code-reviews/{id}

## Jobs

    GET /jobs/{id}

---

# 47. Initial Vertical Slice

The first working API workflow is:

    POST /auth/register
             ↓
    POST /auth/login
             ↓
    POST /organizations
             ↓
    GitHub Installation
             ↓
    GET /organizations/{id}/github/repositories
             ↓
    POST /organizations/{id}/repositories
             ↓
    POST /repositories/{id}/sync
             ↓
    GET /repositories/{id}/sync/status
             ↓
    POST /organizations/{id}/conversations
             ↓
    POST /conversations/{id}/messages
             ↓
    AI Response

Once this workflow works, ForgeAI has its first complete end-to-end
product flow.

---

# 48. API Design Principle

The API should remain:

    Simple
    Predictable
    Versioned
    Secure
    Resource-oriented
    Observable

The API should expose product capabilities rather than exposing internal
implementation details.

For example:

    POST /repositories/{id}/sync

is preferable to exposing:

    POST /kafka/publish/repository-sync

The API describes what the product wants to accomplish.

The internal architecture decides how it is accomplished.