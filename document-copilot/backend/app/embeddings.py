"""Turn text into embedding vectors with the Azure-hosted OpenAI embedding model.

Used by ingestion now (embed every chunk) and by retrieval later (embed the query),
so both sides always use the same model and vector size.
"""

from openai import AsyncOpenAI

from app.config import settings

AZURE_V1_PATH = "/openai/v1"


def create_embedding_client() -> AsyncOpenAI:
    """Client for the Azure OpenAI v1 API: the plain OpenAI SDK pointed at the resource URL.

    The v1 API needs no `api-version` parameter, and `model` is the deployment name.
    """
    base_url = settings.azure_openai_endpoint.rstrip("/")
    if not base_url.endswith(AZURE_V1_PATH):
        base_url += AZURE_V1_PATH
    return AsyncOpenAI(
        base_url=base_url,
        api_key=settings.openai_api_key.get_secret_value(),
        max_retries=5,  # the SDK backs off on rate limits (429) and transient errors
    )


async def embed_texts(client: AsyncOpenAI, texts: list[str]) -> tuple[list[list[float]], int]:
    """Return one vector per text, in the same order, plus the tokens the API billed."""
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
        dimensions=settings.openai_embedding_dimensions,
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in ordered]
    # Fail loudly here rather than at the database: a wrong size means a wrong model/deployment.
    for vector in vectors:
        if len(vector) != settings.openai_embedding_dimensions:
            raise ValueError(
                f"Embedding has {len(vector)} dimensions, expected "
                f"{settings.openai_embedding_dimensions}; check the deployment name."
            )
    return vectors, response.usage.total_tokens
