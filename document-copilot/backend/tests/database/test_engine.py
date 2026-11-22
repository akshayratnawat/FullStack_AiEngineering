"""create_search_engine picks its connection settings from the URL: no network, no database."""

import pytest
from pydantic import SecretStr
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import engine as engine_module

SESSION_URL = "postgresql://user:pw@aws-0-region.pooler.supabase.com:5432/postgres"
TRANSACTION_URL = "postgresql://user:pw@aws-0-region.pooler.supabase.com:6543/postgres"


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace SQLAlchemy's engine factory, recording what it was asked for."""
    seen: dict = {}

    def fake_create_async_engine(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)
    return seen


def use(monkeypatch: pytest.MonkeyPatch, database_url: str, search_url: str | None = None) -> None:
    monkeypatch.setattr(settings, "database_url", SecretStr(database_url))
    monkeypatch.setattr(settings, "search_database_url", SecretStr(search_url) if search_url else None)


def test_a_session_connection_gets_a_small_bounded_pool(monkeypatch, captured):
    use(monkeypatch, SESSION_URL)

    engine_module.create_search_engine()

    # psycopg 3 needs its own driver name in the URL; the default would look for psycopg2.
    assert captured["url"].startswith("postgresql+psycopg://")
    assert captured["kwargs"]["pool_size"] == engine_module.POOL_SIZE
    assert captured["kwargs"]["max_overflow"] == engine_module.MAX_OVERFLOW
    assert engine_module.POOL_SIZE + engine_module.MAX_OVERFLOW < 15  # under the session pooler's limit
    assert "poolclass" not in captured["kwargs"]


def test_the_transaction_pooler_gets_no_pool_and_no_prepared_statements(monkeypatch, captured):
    use(monkeypatch, SESSION_URL, search_url=TRANSACTION_URL)

    engine_module.create_search_engine()

    assert captured["kwargs"]["poolclass"] is NullPool
    # psycopg prepares a query after a few runs by default; the pooler would break that.
    assert captured["kwargs"]["connect_args"] == {"prepare_threshold": None}
    assert ":6543/" in captured["url"]


def test_searches_use_the_database_url_when_no_search_url_is_set(monkeypatch, captured):
    use(monkeypatch, SESSION_URL)

    engine_module.create_search_engine()

    assert ":5432/" in captured["url"]


def test_migrations_stay_on_the_database_url_which_still_refuses_the_transaction_pooler():
    # DATABASE_URL is what Alembic uses and it needs a session connection; only the app's search
    # may use the transaction pooler, through its own setting.
    with pytest.raises(ValueError, match="transaction pooler"):
        settings.reject_transaction_pooler(SecretStr(TRANSACTION_URL))
