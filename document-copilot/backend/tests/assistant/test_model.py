"""Tests for assistant/model.py and the shared endpoint helper. No network: only builds objects."""

from pydantic import SecretStr

from app import embeddings
from app.assistant import model


def fake_settings(endpoint: str):
    """Stand-in settings with just the fields the model builder reads."""

    class Fake:
        azure_openai_endpoint = endpoint
        openai_api_key = SecretStr("test-key")
        openai_chat_model = "my-chat-deployment"

    return Fake()


def test_endpoint_gets_the_v1_path_once(monkeypatch):
    """The endpoint ends in /openai/v1 whether it was written with it, without it, or with a trailing slash."""
    for written in ("https://r.services.ai.azure.com", "https://r.services.ai.azure.com/",
                    "https://r.services.ai.azure.com/openai/v1"):
        monkeypatch.setattr(embeddings, "settings", fake_settings(written))
        assert embeddings.azure_v1_base_url() == "https://r.services.ai.azure.com/openai/v1"


def test_chat_model_uses_the_configured_deployment(monkeypatch):
    """The chat model is built with the configured deployment name and the normalised endpoint."""
    fake = fake_settings("https://r.services.ai.azure.com")
    monkeypatch.setattr(embeddings, "settings", fake)
    monkeypatch.setattr(model, "settings", fake)

    chat_model = model.create_chat_model()

    assert chat_model.model_name == "my-chat-deployment"
    assert str(chat_model.client.base_url).startswith("https://r.services.ai.azure.com/openai/v1")
