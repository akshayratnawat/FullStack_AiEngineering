"""Routes for chat threads and the streaming chat endpoint. Every route needs a signed-in user."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_ai import Agent
from supabase import AsyncClient

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser, get_current_user
from app.chat.messages import ChatStreamRequest, new_user_text, to_ui_message
from app.chat.orchestrator import run_turn
from app.chat.streaming import STREAM_HEADERS
from app.database.chats import ChatStore
from app.database.supabase import create_user_client

router = APIRouter()


class ThreadOut(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class UiMessageOut(BaseModel):
    """A stored message in the AI SDK's shape, ready for `initialMessages`."""

    id: str
    role: Literal["user", "assistant"]
    parts: list[dict]


def get_service_client(request: Request) -> AsyncClient:
    # Created once at startup (see main.py lifespan).
    return request.app.state.service_client


async def get_chat_store(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[AsyncClient, Depends(get_service_client)],
) -> AsyncIterator[ChatStore]:
    # A user client lives for one request, so close its connections afterwards.
    user_client = await create_user_client(user.access_token)
    try:
        yield ChatStore(user_client, service_client)
    finally:
        await user_client.postgrest.aclose()


def get_agent(request: Request) -> Agent[DocumentAgentDeps, GroundedAnswer]:
    # Built once at startup (see main.py lifespan): the agent holds no per-user state.
    return request.app.state.agent


def get_agent_deps(request: Request) -> DocumentAgentDeps:
    # A fresh one per request: `retrieved` must start empty so one turn's evidence never
    # leaks into another's. The engine and client inside are shared, long-lived.
    return DocumentAgentDeps(
        engine=request.app.state.search_engine,
        embedding_client=request.app.state.embedding_client,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
StoreDep = Annotated[ChatStore, Depends(get_chat_store)]
AgentDep = Annotated[Agent[DocumentAgentDeps, GroundedAnswer], Depends(get_agent)]
AgentDepsDep = Annotated[DocumentAgentDeps, Depends(get_agent_deps)]


async def require_own_thread(store: ChatStore, thread_id: UUID, user: CurrentUser) -> None:
    """404 if the thread does not exist, 403 if it belongs to someone else."""
    owner = await store.get_thread_owner(thread_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found.")
    if owner != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This thread belongs to another user.")


@router.get("/threads")
async def list_threads(user: CurrentUserDep, store: StoreDep) -> list[ThreadOut]:
    return [ThreadOut(**row) for row in await store.list_threads()]


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(user: CurrentUserDep, store: StoreDep) -> ThreadOut:
    return ThreadOut(**await store.create_thread(user))


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: UUID, user: CurrentUserDep, store: StoreDep
) -> list[UiMessageOut]:
    await require_own_thread(store, thread_id, user)
    return [UiMessageOut(**to_ui_message(row)) for row in await store.list_messages(thread_id)]


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: CurrentUserDep,
    store: StoreDep,
    agent: AgentDep,
    deps: AgentDepsDep,
) -> StreamingResponse:
    # Everything that can fail with a proper HTTP status happens before the stream starts.
    await require_own_thread(store, body.thread_id, user)
    try:
        user_text = new_user_text(body.messages)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return StreamingResponse(
        run_turn(store, body.thread_id, user_text, agent, deps),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
