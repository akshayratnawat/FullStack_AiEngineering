from pathlib import Path
from urllib.parse import urlparse

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path, so .env is found no matter where the process is started from.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# Every placeholder value in .env.example contains this (e.g. "your-project-ref").
PLACEHOLDER_MARKER = "your-"
# Supabase transaction pooler port; Alembic migrations need a session connection.
TRANSACTION_POOLER_PORT = 6543


class Settings(BaseSettings):
    """All environment config for the backend. Field `foo_bar` reads env var `FOO_BAR`."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Fields without a default are required: startup fails if they are missing.
    # SecretStr hides the value in logs and tracebacks; use .get_secret_value() to read it.
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr
    database_url: SecretStr  # direct/session connection (it contains the DB password)
    openai_api_key: SecretStr  # the Azure AI Foundry / Azure OpenAI resource key
    # Resource URL, e.g. https://<resource>.openai.azure.com (Azure OpenAI v1 API).
    azure_openai_endpoint: str

    # On Azure this is the DEPLOYMENT name you gave the model, not the model name.
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536  # must match the pgvector column size

    # Comma-separated browser origins allowed to call the API (CORS).
    allowed_origins: str = "http://localhost:5173"

    @field_validator(
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "database_url",
        "openai_api_key",
        "azure_openai_endpoint",
    )
    @classmethod
    def reject_placeholders(cls, value: str | SecretStr, info: ValidationInfo) -> str | SecretStr:
        # Catches a copied .env.example whose values were never filled in.
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if PLACEHOLDER_MARKER in raw.lower():
            # Name the field only; never echo the value.
            raise ValueError(f"{info.field_name} still has its .env.example placeholder")
        return value

    @field_validator("database_url")
    @classmethod
    def reject_transaction_pooler(cls, value: SecretStr) -> SecretStr:
        # Only the transaction pooler port is blocked; the session pooler (5432) is fine.
        if urlparse(value.get_secret_value()).port == TRANSACTION_POOLER_PORT:
            raise ValueError(
                "database_url uses the transaction pooler (port 6543); "
                "use the direct or session connection (port 5432)"
            )
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


# Created once at import; every module does `from app.config import settings`.
settings = Settings()
