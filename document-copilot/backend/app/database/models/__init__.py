# Importing every model here registers all tables on Base.metadata,
# which is exactly what Alembic needs: `from app.database.models import Base`.
from app.database.models.base import Base
from app.database.models.chat_messages import ChatMessage, MessageRole
from app.database.models.chat_threads import ChatThread
from app.database.models.document_chunks import EMBEDDING_DIMENSIONS, DocumentChunk
from app.database.models.message_citations import MessageCitation
from app.database.models.source_documents import SourceDocument
from app.database.models.users import User

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Base",
    "ChatMessage",
    "ChatThread",
    "DocumentChunk",
    "MessageCitation",
    "MessageRole",
    "SourceDocument",
    "User",
]
