"""The chat model the agent talks to: an Azure OpenAI deployment, through PydanticAI."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider

from app.config import settings
from app.embeddings import azure_v1_base_url


def create_chat_model() -> OpenAIChatModel:
    """Build the model once at startup. `openai_chat_model` is the Azure deployment name."""
    provider = AzureProvider(
        # The v1 API takes no `api-version`, and the provider omits it for a URL ending in /v1.
        azure_endpoint=azure_v1_base_url(),
        api_key=settings.openai_api_key.get_secret_value(),
    )
    return OpenAIChatModel(settings.openai_chat_model, provider=provider)
