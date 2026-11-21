"""Tests for how app/api/chat.py hands the shared agent pieces to each request.

The engine, embedding client and agent are built once at startup (main.py lifespan) and
live on `app.state`. What must hold is that they are shared, but each turn's `retrieved`
dict is not. A stand-in request with an `app.state` is enough; nothing starts a server.
"""

from types import SimpleNamespace

from app.api.chat import get_agent, get_agent_deps

STATE = SimpleNamespace(search_engine=object(), embedding_client=object(), agent=object())
REQUEST = SimpleNamespace(app=SimpleNamespace(state=STATE))


def test_the_agent_is_the_one_built_at_startup():
    assert get_agent(REQUEST) is STATE.agent


def test_each_request_shares_the_engine_and_client_but_not_the_evidence():
    first, second = get_agent_deps(REQUEST), get_agent_deps(REQUEST)

    assert first.engine is second.engine is STATE.search_engine
    assert first.embedding_client is second.embedding_client is STATE.embedding_client
    first.retrieved["a chunk"] = "seen this turn"
    assert second.retrieved == {}  # one turn's evidence never leaks into another
