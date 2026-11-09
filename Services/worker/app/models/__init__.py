"""
models/__init__.py

Import all models so SQLAlchemy registers them with Base.metadata.
This also allows Base.metadata.create_all() to create worker-owned tables.

Tables OWNED by this worker service:
  - repository_files     (file discovery/change-tracking metadata)
  - repository_knowledge (vector chunk metadata — vectors live in Qdrant)
  - code_symbols         (AST-extracted symbols: functions, classes, routes)
  - code_relationships   (directional relationships between symbols)

Tables READ from repository service (shared PostgreSQL, not owned here):
  - repositories         (to get github_installation_id, default_branch, etc.)
  - repository_syncs     (to update status/progress during sync)
  - github_installations (to get github_installation_id for token exchange)
"""

from app.models.repository_file import RepositoryFile      # noqa: F401
from app.models.repository_knowledge import RepositoryKnowledge  # noqa: F401
from app.models.code_symbol import CodeSymbol                    # noqa: F401
from app.models.code_relationship import CodeRelationship        # noqa: F401
from app.models.repo_map import RepositoryMap                    # noqa: F401


# These are read-only mirror models — we define them here so SQLAlchemy
# can query them without an inter-service HTTP call.
from app.models.mirrors import Repository, RepositorySync, GitHubInstallation  # noqa: F401
