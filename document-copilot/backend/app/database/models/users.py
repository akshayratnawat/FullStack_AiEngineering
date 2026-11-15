import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin


class User(CreatedAtMixin, Base):
    """One row per signed-in analyst; `id` is the Supabase `auth.users.id`."""

    __tablename__ = "users"

    # No default: the id comes from Supabase Auth. The foreign key to auth.users
    # lives in the migration, because the `auth` schema is not part of our models.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)

    threads: Mapped[list["ChatThread"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
