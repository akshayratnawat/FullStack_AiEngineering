import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# Must equal settings.openai_embedding_dimensions (text-embedding-3-small = 1536).
# Kept as a constant so importing the models never needs a .env file.
EMBEDDING_DIMENSIONS = 1536


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A retrieval-ready passage of a filing, searchable by meaning and by keyword."""

    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)  # position within the document
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String)
    token_count: Mapped[int] = mapped_column(Integer)
    # Nullable so chunks can be stored first and embedded afterwards.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # Maintained by Postgres itself: never written by our code, always in sync with `content`.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    # ticker, company, filing type/date, year, accession number, source offsets...
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    document: Mapped["SourceDocument"] = relationship(back_populates="chunks")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        # Full-text (keyword) search. Declared here, not only in the migration, so
        # that autogenerate knows the index exists and never proposes to drop it.
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        # Semantic (meaning) search: approximate nearest neighbours by cosine distance.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
