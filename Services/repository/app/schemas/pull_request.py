"""
pull_request.py — Response schemas for the pull request endpoints.

Pull requests are read live from GitHub through the GitHub App installation;
the Repository Service does not store them.
"""
from pydantic import BaseModel


class PullRequestSummary(BaseModel):
    number: int
    title: str
    # open | closed | merged
    state: str
    draft: bool = False
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    head_sha: str | None = None
    html_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PullRequestListResponse(BaseModel):
    pull_requests: list[PullRequestSummary]
    page: int
    limit: int


class PullRequestFile(BaseModel):
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0
    # Unified diff. GitHub omits it for binary or very large files.
    patch: str | None = None


class PullRequestDetail(PullRequestSummary):
    body: str | None = None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    files: list[PullRequestFile]
    # True when the PR has more files than were returned.
    files_truncated: bool = False
