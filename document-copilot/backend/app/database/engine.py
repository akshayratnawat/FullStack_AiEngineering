"""SQL engine for retrieval queries (pgvector and full-text search).

The Supabase API client can't order by vector distance, so retrieval talks to Postgres
directly. The filing corpus is shared and read-only, so no per-user RLS applies here.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings


def create_search_engine() -> AsyncEngine:
    """Create once at startup and keep on `app.state`; dispose it on shutdown."""
    # A plain "postgresql://" would make SQLAlchemy look for the older psycopg2 driver.
    url = settings.database_url.get_secret_value().replace("postgresql://", "postgresql+psycopg://", 1)
    return create_async_engine(url, pool_pre_ping=True)
