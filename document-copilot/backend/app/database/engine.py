"""SQL engine for retrieval queries (pgvector and full-text search).

The Supabase API client can't order by vector distance, so retrieval talks to Postgres
directly. The filing corpus is shared and read-only, so no per-user RLS applies here.
"""

from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import TRANSACTION_POOLER_PORT, settings

# A session pooler or direct connection has a small hard limit on clients (Supabase's session
# pooler allowed 15 when this was written). One process keeps well under it: SQLAlchemy's default
# of 5 + 10 extra exhausted it during a run of the client brief.
POOL_SIZE = 3
MAX_OVERFLOW = 2


def create_search_engine() -> AsyncEngine:
    """Create once at startup and keep on `app.state`; dispose it on shutdown."""
    raw_url = settings.search_url.get_secret_value()
    # A plain "postgresql://" would make SQLAlchemy look for the older psycopg2 driver.
    url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)

    if urlparse(raw_url).port == TRANSACTION_POOLER_PORT:
        # Supabase's transaction pooler (the setup on Vercel). It is the pool, shared by every
        # function instance, so ours keeps no connections: NullPool opens one per query and
        # lets go. It also hands each query to whichever database connection is free, so a
        # prepared statement made on one would not exist on the next: turn preparing off.
        return create_async_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})

    return create_async_engine(url, pool_pre_ping=True, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW)
