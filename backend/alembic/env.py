from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from alembic import context
from app.config import get_settings
from app.database import Base

# Import all models so they're registered with Base

# this is the Alembic Config object
config = context.config

# NOTE: Do NOT call fileConfig(config.config_file_name) here.
# Alembic's env.py template includes that call to set up logging from
# alembic.ini, but fileConfig defaults to disable_existing_loggers=True
# which silently disables every logger not listed in the config —
# including "app". This kills the RotatingFileHandler on the "app"
# logger and all runtime log messages stop writing to the log file.
# Alembic's own log messages propagate through the normal hierarchy.

# Set database URL from settings
settings = get_settings()
database_url = settings.database_url
# Use psycopg2 (sync) for migrations — avoids async/sync event loop conflicts
# when running from init_db() via run_in_executor
if "+asyncpg" in database_url:
    database_url = database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", database_url)

# add your model's MetaData object here
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using sync psycopg2."""
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
