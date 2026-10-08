# Import all models here so SQLAlchemy's metadata is fully populated
# before create_all() is called.
# Order matters: models with no FK dependencies first.
from app.models.github_installation import GitHubInstallation  # noqa: F401
from app.models.repository import Repository                    # noqa: F401
from app.models.repository_sync import RepositorySync          # noqa: F401
