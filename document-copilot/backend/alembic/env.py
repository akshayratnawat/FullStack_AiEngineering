from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.config import settings
from app.database.models import (
    Base,  # importing this registers every table on Base.metadata
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What autogenerate compares the real database against.
target_metadata = Base.metadata


def get_url() -> str:
    # One source of truth for the connection string: app.config.settings (never alembic.ini).
    # SQLAlchemy needs to be told to use the psycopg 3 driver we have installed;
    # a plain "postgresql://" would make it look for the older psycopg2.
    url = settings.database_url.get_secret_value()
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (no database connection)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run the migrations."""
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # also notice when a column's type changes
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
