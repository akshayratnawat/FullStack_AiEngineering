import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.assistant.agent import create_agent
from app.config import settings  # importing this also validates all env config
from app.database.engine import create_search_engine
from app.database.supabase import create_service_client
from app.embeddings import create_embedding_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One service-role client for the whole process; user clients are made per request.
    app.state.service_client = await create_service_client()
    # Shared by every request: the retrieval SQL engine, the embedding client and the agent.
    app.state.search_engine = create_search_engine()
    app.state.embedding_client = create_embedding_client()
    app.state.agent = create_agent()
    yield
    await app.state.service_client.postgrest.aclose()
    await app.state.search_engine.dispose()


app = FastAPI(title="Document Copilot", lifespan=lifespan)

# The browser app runs on another origin (localhost:5173), so the API must allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    # `python -m app.main`. On Windows, uvicorn's default event loop (Proactor) cannot run
    # psycopg's async mode, which the retrieval queries use, so start the server on the
    # selector loop explicitly. (`uvicorn app.main:app --reload` also uses it; plain
    # `uvicorn app.main:app` on Windows does not. Linux and Railway are unaffected.)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, loop="none"))
    asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
