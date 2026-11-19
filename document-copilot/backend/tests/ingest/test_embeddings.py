"""Unit tests for the Azure embedding helper. No network: the client is a fake."""

import asyncio
from types import SimpleNamespace

import pytest

from app import embeddings
from app.config import settings


class FakeClient:
    def __init__(self, vector_size: int) -> None:
        self.vector_size = vector_size
        self.requests = []
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        # Return items out of order, as an API is allowed to, to prove we re-sort them.
        data = [
            SimpleNamespace(index=i, embedding=[float(i)] * self.vector_size)
            for i in reversed(range(len(kwargs["input"])))
        ]
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=7))


def test_vectors_come_back_in_input_order_with_the_billed_tokens():
    client = FakeClient(settings.openai_embedding_dimensions)
    vectors, tokens = asyncio.run(embeddings.embed_texts(client, ["a", "b", "c"]))
    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]
    assert tokens == 7


def test_request_names_the_deployment_and_the_vector_size():
    client = FakeClient(settings.openai_embedding_dimensions)
    asyncio.run(embeddings.embed_texts(client, ["a"]))
    assert client.requests[0]["model"] == settings.openai_embedding_model
    assert client.requests[0]["dimensions"] == settings.openai_embedding_dimensions


def test_wrong_vector_size_fails_loudly():
    client = FakeClient(vector_size=3)
    with pytest.raises(ValueError, match="dimensions"):
        asyncio.run(embeddings.embed_texts(client, ["a"]))
