# Import all models here so SQLAlchemy's metadata is fully populated
# before create_all() is called. Order matters: independent models first.
from app.models.user import User  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.membership import Membership  # noqa: F401
