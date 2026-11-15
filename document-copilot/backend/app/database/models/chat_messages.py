import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One user question or assistant answer inside a thread."""

    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    # Store the lowercase values ("user"), not the Python names ("USER").
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=lambda e: [m.value for m in e])
    )
    content: Mapped[str] = mapped_column(Text)  # plain text of the message
    # AI SDK-compatible message parts, kept so the thread reloads exactly as streamed.
    parts: Mapped[list | None] = mapped_column(JSONB)
    # Model name, token counts and similar, for assistant messages.
    usage: Mapped[dict | None] = mapped_column(JSONB)

    thread: Mapped["ChatThread"] = relationship(back_populates="messages")  # noqa: F821
    citations: Mapped[list["MessageCitation"]] = relationship(  # noqa: F821
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageCitation.citation_index",
    )
