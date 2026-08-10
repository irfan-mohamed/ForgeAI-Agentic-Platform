# ForgeAI — User Flow

## 1. Purpose

This document describes the complete user journey through the initial ForgeAI product.

It focuses on what the user does, what the system does in response, and what the user sees at each stage.

Technical implementation details are intentionally excluded from this document.

---

# 2. Overall User Journey

The initial ForgeAI journey is:

    Landing Page
         ↓
    Registration
         ↓
    Login
         ↓
    Create Organization
         ↓
    Connect GitHub
         ↓
    Select Repository
         ↓
    Repository Synchronization
         ↓
    Repository Analysis
         ↓
    Knowledge Creation
         ↓
    Repository Ready
         ↓
    AI Workspace
         ↓
    Repository Questions / Code Review / Test Assistance


The primary goal of the initial user journey is to take a user from
having no connected project to having an AI system that understands
their software repository.

---

# 3. Landing Page

## User Action

The user opens ForgeAI.

## User Sees

The landing page explains:

- What ForgeAI is
- What problem it solves
- Main capabilities
- How it works
- Sign Up
- Login

The primary action is:

> Get Started

The user can either register for a new account or log into an existing account.

---

# 4. Registration

## User Action

The user selects:

> Create Account

The registration form asks for the minimum information required to create a ForgeAI account.

Example:

- Name
- Email
- Password
- Password confirmation

## System Action

ForgeAI:

1. Validates the submitted information.
2. Checks whether the email is already registered.
3. Creates the user account.
4. Creates the user's initial session.
5. Redirects the user to the organization setup flow.

## User Sees

A successful registration message.

Example:

> Welcome to ForgeAI.

The user is then asked to create or join an organization.

---

# 5. Login

## User Action

An existing user enters:

- Email
- Password

and selects:

> Login

## System Action

ForgeAI validates the credentials.

If successful, the user is taken to their ForgeAI workspace.

If the user belongs to multiple organizations, the user is asked to select an organization.

## Failed Login

If authentication fails, ForgeAI displays a clear error without revealing sensitive information.

Example:

> Invalid email or password.

---

# 6. Organization Creation

A ForgeAI user works inside an organization.

## User Action

After registration, the user selects:

> Create Organization

The user provides:

- Organization name
- Optional organization description

Example:

    Organization Name:
    Acme Engineering

## System Action

ForgeAI creates the organization and makes the user its initial owner.

The organization becomes the user's primary workspace.

## User Sees

The organization dashboard.

Example:

    Acme Engineering

    Repositories
    AI Workspace
    Members
    Settings

Because the organization currently has no repositories, ForgeAI guides the user toward connecting GitHub.

---

# 7. Connect GitHub

## User Action

The user selects:

> Connect GitHub

ForgeAI explains that repository access is controlled through GitHub.

The user continues to GitHub to authorize the ForgeAI GitHub App.

---

# 8. GitHub Authorization

The user arrives at GitHub.

GitHub shows the permissions and repository access associated with the ForgeAI GitHub App.

The user chooses where ForgeAI should be installed.

This may be:

- Personal GitHub account
- GitHub organization

The user can grant access to:

- All repositories
- Selected repositories

ForgeAI should encourage selected-repository access when appropriate.

The user confirms the installation.

---

# 9. Public and Private Repositories

ForgeAI supports both public and private repositories.

## Public Repository

The user can select a public repository that is available through the GitHub connection.

## Private Repository

A private repository is only available when the GitHub App has been granted access to it.

The user must explicitly grant ForgeAI access to the repository.

Example:

    GitHub

    Repository Access

    ✓ backend
    ✓ payment-service
    ✗ internal-tools

ForgeAI can only work with repositories that GitHub has made available to the application.

---

# 10. Repository Selection

After GitHub authorization, ForgeAI displays the repositories available through the GitHub connection.

Example:

    Your Repositories

    ┌──────────────────────────────┐
    │ payment-service              │
    │ Python                       │
    │ Private                      │
    │                              │
    │ [Connect]                    │
    └──────────────────────────────┘

    ┌──────────────────────────────┐
    │ frontend                     │
    │ TypeScript                   │
    │ Private                      │
    │                              │
    │ [Connect]                    │
    └──────────────────────────────┘

The user selects:

> Connect

for the desired repository.

---

# 11. Repository Connection

Once the user selects a repository, ForgeAI creates a connection between:

    ForgeAI Organization
             ↓
    GitHub Connection
             ↓
    GitHub Repository

The repository now appears inside the ForgeAI organization.

---

# 12. Repository Synchronization

After connection, ForgeAI begins synchronizing the repository.

The user does not need to manually upload files.

ForgeAI retrieves the information required to understand the repository.

The user sees a progress screen.

Example:

    Connecting repository...

    ✓ Repository connected
    ✓ Repository structure discovered
    ● Reading source files
    ○ Processing documentation
    ○ Building repository knowledge
    ○ Preparing AI workspace

The user can leave this page while processing continues.

---

# 13. Repository Analysis

ForgeAI examines the repository.

The initial analysis attempts to understand:

- Repository structure
- Programming languages
- Important directories
- Source files
- Documentation
- Configuration
- APIs
- Dependencies
- Relationships between components

The goal is not simply to store files.

The goal is to create an understanding of the software system.

---

# 14. Knowledge Creation

After repository analysis, ForgeAI creates the knowledge required by the AI workspace.

The system should be able to understand questions such as:

> Where is authentication implemented?

> Which service handles payments?

> How does this API work?

> Which files are related to user registration?

> What happens when an order is created?

The repository is now considered ready for AI interaction.

---

# 15. Repository Ready

When processing is complete, ForgeAI displays:

    ✓ Repository Ready

    Repository:
    payment-service

    Files analyzed:
    1,284

    Documentation:
    36 files

    Languages:
    Python / TypeScript

    Components discovered:
    18

The primary action is:

> Open AI Workspace

---

# 16. AI Workspace

The AI Workspace is the main interaction area.

The user can ask questions about the connected repository.

Example:

    User:

    "How does authentication work in this project?"

    ForgeAI:

    "Authentication is handled by..."

The answer should be based on the connected repository and its available engineering knowledge.

---

# 17. Repository Questions

The user can ask questions such as:

### Understanding

> Explain this repository.

> Explain the payment service.

> Where is authentication implemented?

> How does the order flow work?

### Finding Code

> Where is the user registration logic?

> Find all places where payments are processed.

> Which files call this API?

### Impact Analysis

> What could be affected if I change this function?

> Which services depend on this module?

### Development Assistance

> How should I implement this feature?

> What files should I modify?

The AI should provide relevant explanations and repository references.

---

# 18. Pull Request / Code Review

A connected repository can also be used for AI-assisted code review.

## User Action

A developer creates or selects a Pull Request.

ForgeAI receives the Pull Request information.

## System Action

ForgeAI analyzes the changes in the context of the repository.

The review may look for:

- Potential bugs
- Code quality problems
- Security concerns
- Architecture issues
- Missing tests
- Maintainability problems

## User Sees

A review summary.

Example:

    Pull Request #42

    Overall Assessment: Needs Attention

    Findings:
    
    Critical: 0
    High: 1
    Medium: 2
    Low: 3

    Test Coverage: Missing tests for payment failure path

The user can inspect individual findings.

---

# 19. Test Assistance

The user can ask ForgeAI for test assistance.

Example:

> Generate tests for this change.

ForgeAI analyzes the relevant code and proposes tests.

The user can review the generated tests before applying them.

The initial version should prioritize recommendations and generated code that the developer can inspect rather than automatically changing the repository without confirmation.

---

# 20. Repository Updates

Repositories change continuously.

When new commits are pushed, ForgeAI should eventually update its understanding of the repository.

The conceptual flow is:

    Repository Updated
           ↓
    ForgeAI Detects Change
           ↓
    Updated Files Identified
           ↓
    Repository Knowledge Updated
           ↓
    AI Workspace Uses Updated Knowledge

The user should not need to manually re-upload the repository.

---

# 21. Disconnecting a Repository

The user can disconnect a repository from ForgeAI.

## User Action

    Repository Settings
           ↓
    Disconnect Repository

## System Action

ForgeAI stops treating the repository as an active connected repository.

The user should be informed about what happens to the repository's stored knowledge and generated information.

The exact retention and deletion policy will be defined separately.

---

# 22. Revoking GitHub Access

A user or organization administrator may revoke ForgeAI's GitHub access directly from GitHub.

If access is revoked, ForgeAI must recognize that the repository is no longer accessible.

The repository should be marked accordingly.

Example:

    Repository Access Lost

    ForgeAI can no longer access this repository.

    Reconnect GitHub to restore access.

ForgeAI must not continue attempting to access a repository after its authorization has been revoked.

---

# 23. Organization Members

The initial organization model supports multiple users.

Example:

    Acme Engineering

    Owner
    ├── Irfan

    Members
    ├── Developer A
    ├── Developer B
    └── DevOps Engineer

Organization members can eventually have different permissions.

The detailed role and permission model will be defined separately.

---

# 24. Multiple Organizations

A ForgeAI user may eventually belong to multiple organizations.

Example:

    Irfan

    ├── Personal Projects
    │      └── portfolio
    │
    └── Acme Engineering
           ├── backend
           ├── frontend
           └── payment-service

The user can switch between organizations.

Data and repository knowledge must remain isolated between organizations.

---

# 25. Complete Initial Flow

The complete initial user experience is:

    ┌───────────────────────┐
    │       ForgeAI         │
    │     Landing Page      │
    └───────────┬───────────┘
                │
                ↓
        Register / Login
                │
                ↓
       Create Organization
                │
                ↓
          Connect GitHub
                │
                ↓
      GitHub App Authorization
                │
                ↓
       Select Repository
                │
                ↓
       Connect Repository
                │
                ↓
      Repository Synchronization
                │
                ↓
       Repository Analysis
                │
                ↓
       Knowledge Creation
                │
                ↓
        Repository Ready
                │
                ↓
          AI Workspace
                │
       ┌────────┼─────────┐
       ↓        ↓         ↓
    Ask AI   Code Review  Tests
       │        │         │
       └────────┼─────────┘
                ↓
          Developer Work

---

# 26. MVP User Flow

The first working version does not need to implement every future capability.

The minimum complete user journey is:

    Register
       ↓
    Login
       ↓
    Create Organization
       ↓
    Connect GitHub
       ↓
    Select Repository
       ↓
    Synchronize Repository
       ↓
    Analyze Repository
       ↓
    Build Knowledge
       ↓
    Ask Questions
       ↓
    Receive Repository-Aware Answers

Once this flow works reliably, AI Code Review and Test Assistance can be added.

---

# 27. Product Principle

The user should experience ForgeAI as one platform.

They should not need to understand:

- Agents
- RAG
- Vector databases
- Message queues
- Microservices
- Kubernetes
- LLM providers

Those are implementation details.

The user experience should remain simple:

> Connect your software and work with an AI that understands it.