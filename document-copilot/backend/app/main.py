from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.config import settings  # importing this also validates all env config
from app.database.supabase import create_service_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One service-role client for the whole process; user clients are made per request.
    app.state.service_client = await create_service_client()
    yield
    await app.state.service_client.postgrest.aclose()


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
    uvicorn.run("app.main:app", host="127.0.0.1",
                port=8000)
