import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# -- Alembic Config object ----------------------------------------------------
config = context.config

# -- Logging ------------------------------------------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -- Override sqlalchemy.url from environment (12-factor) ---------------------
# DATABASE_URL set in .env or via docker-compose environment.
# configparser uses % for interpolation, so we must escape % as %% before
# passing the URL through set_main_option (e.g. %40 → %%40).
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# -- Import all models so autogenerate can see them ---------------------------
# Side-effect import registers all models with Base.metadata.
import app.models  # noqa: F401, E402

from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
