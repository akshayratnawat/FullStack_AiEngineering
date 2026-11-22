"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-15

Creates the six tables, the pgvector extension, the search indexes and the
row-level security (RLS) policies.

Written by hand (autogenerate could not reach the database). After applying it,
`alembic revision --autogenerate` should report no differences from the models.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Extension: must exist before any table uses the `vector` type ---------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- 2. Tables, parents before children ----------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        # The id IS the Supabase Auth id; deleting the login deletes the row.
        sa.ForeignKeyConstraint(
            ["id"], ["auth.users.id"], name="fk_users_id_users", ondelete="CASCADE"
        ),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("cik", sa.String(), nullable=False),
        sa.Column("form", sa.String(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_source_documents"),
        sa.UniqueConstraint("accession_number", name="uq_source_documents_accession_number"),
    )
    op.create_index("ix_source_documents_ticker", "source_documents", ["ticker"])
    op.create_index("ix_source_documents_fiscal_year", "source_documents", ["fiscal_year"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        # Postgres keeps this in sync with `content` by itself.
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=False,
        ),
        sa.Column("chunk_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name="fk_document_chunks_document_id_source_documents",
            ondelete="CASCADE",
        ),
    )
    # Keyword search (GIN) and meaning search (HNSW, cosine distance).
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "chat_threads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chat_threads"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_chat_threads_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", name="message_role"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            name="fk_chat_messages_thread_id_chat_threads",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])

    op.create_table(
        "message_citations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_message_citations"),
        sa.UniqueConstraint("message_id", "citation_index", name="uq_message_citations_message_id"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name="fk_message_citations_message_id_chat_messages",
            ondelete="CASCADE",
        ),
        # SET NULL: re-ingesting replaces chunks, old answers keep their excerpt snapshot.
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_message_citations_chunk_id_document_chunks",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])
    op.create_index("ix_message_citations_chunk_id", "message_citations", ["chunk_id"])

    # --- 3. Row-level security -------------------------------------------------------
    # The backend connects as the database owner / service role, which bypasses RLS.
    # These policies protect the tables if anyone reaches them with a user's token
    # (for example through Supabase's own API): each user sees only their own data.
    for table in (
        "users",
        "source_documents",
        "document_chunks",
        "chat_threads",
        "chat_messages",
        "message_citations",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # `(select auth.uid())` is evaluated once per query instead of once per row.
    op.execute("""
        CREATE POLICY users_select_own ON users FOR SELECT TO authenticated
        USING (id = (select auth.uid()))
    """)
    op.execute("""
        CREATE POLICY chat_threads_own ON chat_threads FOR ALL TO authenticated
        USING (user_id = (select auth.uid()))
        WITH CHECK (user_id = (select auth.uid()))
    """)
    op.execute("""
        CREATE POLICY chat_messages_own ON chat_messages FOR ALL TO authenticated
        USING (EXISTS (
            SELECT 1 FROM chat_threads t
            WHERE t.id = chat_messages.thread_id AND t.user_id = (select auth.uid())
        ))
        WITH CHECK (EXISTS (
            SELECT 1 FROM chat_threads t
            WHERE t.id = chat_messages.thread_id AND t.user_id = (select auth.uid())
        ))
    """)
    op.execute("""
        CREATE POLICY message_citations_own ON message_citations FOR ALL TO authenticated
        USING (EXISTS (
            SELECT 1 FROM chat_messages m JOIN chat_threads t ON t.id = m.thread_id
            WHERE m.id = message_citations.message_id AND t.user_id = (select auth.uid())
        ))
        WITH CHECK (EXISTS (
            SELECT 1 FROM chat_messages m JOIN chat_threads t ON t.id = m.thread_id
            WHERE m.id = message_citations.message_id AND t.user_id = (select auth.uid())
        ))
    """)
    # The filing corpus is shared: any signed-in user may read it, nobody may write
    # it through a user token (ingestion uses the service role).
    op.execute("""
        CREATE POLICY source_documents_read ON source_documents FOR SELECT TO authenticated
        USING (true)
    """)
    op.execute("""
        CREATE POLICY document_chunks_read ON document_chunks FOR SELECT TO authenticated
        USING (true)
    """)


def downgrade() -> None:
    # Dropping a table also drops its indexes and policies. Children first.
    op.drop_table("message_citations")
    op.drop_table("chat_messages")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.drop_table("chat_threads")
    op.drop_table("document_chunks")
    op.drop_table("source_documents")
    op.drop_table("users")
    # The vector extension is left installed on purpose: other things may use it.
