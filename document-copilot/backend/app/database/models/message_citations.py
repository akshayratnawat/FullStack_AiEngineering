import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class MessageCitation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A source passage that an assistant message cites."""

    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    # SET NULL, not CASCADE: re-ingesting a filing replaces its chunks, but an old
    # answer must keep showing what it cited. The snapshot columns below make that possible.
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), index=True
    )
    citation_index: Mapped[int] = mapped_column(Integer)  # the [1], [2]... order in the answer
    excerpt: Mapped[str] = mapped_column(Text)  # snapshot of the cited text
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String)

    message: Mapped["ChatMessage"] = relationship(back_populates="citations")  # noqa: F821
    chunk: Mapped["DocumentChunk | None"] = relationship()  # noqa: F821

    __table_args__ = (UniqueConstraint("message_id", "citation_index"),)
