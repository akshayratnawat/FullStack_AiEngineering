from datetime import date

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class SourceDocument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One SEC filing, with its normalized Markdown text."""

    __tablename__ = "source_documents"

    ticker: Mapped[str] = mapped_column(String, index=True)
    cik: Mapped[str] = mapped_column(String)
    form: Mapped[str] = mapped_column(String)  # e.g. "10-K"
    filing_date: Mapped[date] = mapped_column(Date)
    report_date: Mapped[date] = mapped_column(Date)  # end of the fiscal period
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    # Unique, so re-running ingestion can skip filings that are already stored.
    accession_number: Mapped[str] = mapped_column(String, unique=True)
    source_url: Mapped[str] = mapped_column(String)
    content_markdown: Mapped[str] = mapped_column(Text)
    # Anything extra from manifest.json that has no column of its own.
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    chunks: Mapped[list["DocumentChunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan"
    )
