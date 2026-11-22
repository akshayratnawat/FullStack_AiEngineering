"""Who am I, and may I ask questions? The browser asks once after sign-in."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, can_use_llm, get_current_user

router = APIRouter()


class AccountOut(BaseModel):
    id: UUID
    email: str
    # False for a visitor: they can look around, but asking would spend the owner's model key.
    can_ask: bool


@router.get("/me")
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> AccountOut:
    return AccountOut(id=user.id, email=user.email, can_ask=can_use_llm(user.email))
