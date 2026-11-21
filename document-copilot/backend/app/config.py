from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, ValidationInfo, field_validator
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

    # On Azure these are DEPLOYMENT names you gave the models, not the model names.
    # The chat model writes the answers; it is a different deployment from the embedding one.
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536  # must match the pgvector column size

    # Comma-separated browser origins allowed to call the API (CORS).
    allowed_origins: str = "http://localhost:5173"

    # --- Agent: hard caps for ONE question, so a confused or looping model cannot run up a
    # bill. A comparison across 4 companies needs roughly 8-10 tool calls; "for each company"
    # across all 8 needs about 20 (the live run of the client brief hit 15 and 18). ---
    # How many times the model may be sent back to fix a rejected answer (bad citations or format)
    # before the question is refused. The first spec said one; two rescued about half of the
    # refusals in the live runs (docs/live_verification.md).
    agent_output_retries: int = Field(default=2, ge=0)
    agent_max_tool_calls: int = Field(default=25, ge=1)  # searches + reads per question
    agent_max_model_requests: int = Field(default=30, ge=1)  # round trips to the chat model
    # Counts every request's full context again, so it grows fast: 15 searches of ~5k tokens each; the live brief run hit 500,000 twice.
    agent_max_total_tokens: int = Field(default=800_000, ge=1)

    # How many of the thread's most recent stored messages (questions and answers together)
    # the agent sees as context, so follow-ups like "and for 2023?" make sense. 0 = none.
    agent_history_messages: int = Field(default=10, ge=0)

    # --- Retrieval (see app/retrieval/README.md). Each can be overridden by an env var,
    # e.g. RETRIEVAL_TOP_K=10. ---
    retrieval_top_k: int = Field(default=8, ge=1)  # passages returned after fusion
    retrieval_candidates: int = Field(default=30, ge=1)  # chunks each search returns before fusion
    retrieval_neighbor_window: int = Field(default=1, ge=0)  # chunks added each side of a hit; 0 = none
    retrieval_rrf_k: int = Field(default=60, ge=1)  # smoothing constant in 1 / (k + rank)

    # Words the keyword search ignores, in addition to the English stopwords (the, of, was...)
    # that Postgres already drops. These are filler or words that appear in almost every filing,
    # so matching them says nothing about relevance. Lower-case. As an env var it must be JSON:
    # KEYWORD_IGNORE_WORDS='["tell","company"]' (this replaces the whole list).
    keyword_ignore_words: list[str] = [
        # request filler
        "tell", "show", "give", "please", "explain", "describe", "summarize", "summarise",
        "list", "compare", "comparing", "provide", "find", "say", "says", "said", "mention",
        "mentioned", "discuss", "discussed", "according", "regarding", "about", "across",
        "between", "overall", "based", "using", "use", "need", "want", "know", "help",
        # generic filing words, present in every chunk
        "company", "companies", "filing", "filings", "report", "reported", "reports",
        "annual", "form", "10", "k", "q", "s",
        # vague connectors that carry no topic
        "also", "many", "much", "main", "key", "major", "important", "different",
        "specific", "particular", "related", "within", "during", "among",
    ]

    @field_validator(
        "supabase_url",
        "supabase_anon_key",
        "supabase_service_role_key",
        "database_url",
        "openai_api_key",
        "azure_openai_endpoint",
        "openai_chat_model",
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
