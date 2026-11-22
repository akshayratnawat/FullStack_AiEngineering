"""Chat threads and messages: every database read and write the chat feature needs.

Two Supabase clients are involved, on purpose:
- the user client acts as the caller, so row-level security limits every query to
  that user's own rows;
- the service client bypasses RLS and is used only for the two things the user
  client cannot do: look up who owns a thread (RLS would just hide another user's
  thread, and we want to tell "not yours" from "doesn't exist"), and create the
  `users` row (the table is read-only for signed-in users).

We talk to Postgres through the Supabase API here, not through SQLAlchemy, so the
Python-side defaults on the models (new ids, `updated_at` on update) do not apply:
this module sets them itself.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from supabase import AsyncClient

from app.auth.dependencies import CurrentUser


def citation_rows(message_id: UUID, citations: list[dict]) -> list[dict]:
    """The `message_citations` rows for one answer, from the sources streamed with it.

    The excerpt and section are copied here (not looked up later), so the answer keeps
    showing what it cited even if the filing is re-ingested and its chunks are replaced.
    """
    return [
        {
            "id": str(uuid4()),
            "message_id": str(message_id),
            "chunk_id": citation["chunk_id"],
            "citation_index": citation["marker"],
            "excerpt": citation["excerpt"],
            "section": citation["section"],
            "page": None,  # the filings are split by section, not page
        }
        for citation in citations
    ]


class ChatStore:
    def __init__(self, user_client: AsyncClient, service_client: AsyncClient) -> None:
        self._user = user_client
        self._service = service_client

    async def list_threads(self) -> list[dict]:
        # No user filter needed: RLS only returns the caller's threads.
        result = await (
            self._user.table("chat_threads")
            .select("id, title, created_at, updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        return result.data

    async def create_thread(self, user: CurrentUser) -> dict:
        # Nothing creates the `users` row at sign-up, and chat_threads has a foreign
        # key to it, so make sure it exists. A no-op when it already does.
        await (
            self._service.table("users")
            .upsert(
                {"id": str(user.id), "email": user.email},
                on_conflict="id",
                ignore_duplicates=True,
            )
            .execute()
        )
        result = await (
            self._user.table("chat_threads")
            .insert({"id": str(uuid4()), "user_id": str(user.id)})
            .execute()
        )
        return result.data[0]

    async def get_thread_owner(self, thread_id: UUID) -> UUID | None:
        """The owner's id, or None when no such thread exists."""
        result = await (
            self._service.table("chat_threads")
            .select("user_id")
            .eq("id", str(thread_id))
            .execute()
        )
        return UUID(result.data[0]["user_id"]) if result.data else None

    async def delete_thread(self, thread_id: UUID) -> None:
        # The database cascades: the thread's messages go with it, and their citations
        # with them. RLS means a user's client can only ever delete their own thread.
        await self._user.table("chat_threads").delete().eq("id", str(thread_id)).execute()

    async def rename_thread(self, thread_id: UUID, title: str) -> dict:
        result = await (
            self._user.table("chat_threads")
            .update({"title": title})
            .eq("id", str(thread_id))
            .execute()
        )
        return result.data[0]

    async def get_thread_title(self, thread_id: UUID) -> str | None:
        result = await (
            self._user.table("chat_threads")
            .select("title")
            .eq("id", str(thread_id))
            .execute()
        )
        return result.data[0]["title"] if result.data else None

    async def list_messages(self, thread_id: UUID) -> list[dict]:
        result = await (
            self._user.table("chat_messages")
            .select("id, role, content, parts, created_at")
            .eq("thread_id", str(thread_id))
            .order("created_at")
            .execute()
        )
        return result.data

    async def save_turn(
        self,
        thread_id: UUID,
        user_text: str,
        user_parts: list[dict],
        assistant_text: str,
        assistant_parts: list[dict],
        asked_at: datetime,
        set_title: str | None,
        citations: list[dict] | None = None,
    ) -> None:
        """Store one finished exchange: the user's question and the assistant's answer.

        `citations` are the sources of the answer (the entries of its `data-citations`
        part). They are stored twice on purpose: inside the message's `parts`, which is
        what a reloaded thread shows, and as `message_citations` rows, which can be queried.
        """
        # Both rows go in one request, so they are saved together or not at all. They
        # would also get the same database `now()`, which would leave their order
        # undefined, so the timestamps are set here: question first, answer after.
        answered_at = max(datetime.now(UTC), asked_at)
        user_id, assistant_id = uuid4(), uuid4()
        await (
            self._user.table("chat_messages")
            .insert(
                [
                    {
                        "id": str(user_id),
                        "thread_id": str(thread_id),
                        "role": "user",
                        "content": user_text,
                        "parts": user_parts,
                        "created_at": asked_at.isoformat(),
                    },
                    {
                        "id": str(assistant_id),
                        "thread_id": str(thread_id),
                        "role": "assistant",
                        "content": assistant_text,
                        "parts": assistant_parts,
                        "created_at": answered_at.isoformat(),
                    },
                ]
            )
            .execute()
        )
        if citations:
            try:
                await (
                    self._user.table("message_citations")
                    .insert(citation_rows(assistant_id, citations))
                    .execute()
                )
            except Exception:
                # A second request cannot join the first one's transaction. Remove the
                # exchange (its citations cascade) so the user sees an error AND nothing
                # is stored, and asking again does not leave a duplicate question behind.
                await (
                    self._user.table("chat_messages")
                    .delete()
                    .in_("id", [str(user_id), str(assistant_id)])
                    .execute()
                )
                raise
        # Moves the thread to the top of the sidebar; the first exchange also names it.
        changes: dict = {"updated_at": answered_at.isoformat()}
        if set_title is not None:
            changes["title"] = set_title
        await (
            self._user.table("chat_threads")
            .update(changes)
            .eq("id", str(thread_id))
            .execute()
        )
