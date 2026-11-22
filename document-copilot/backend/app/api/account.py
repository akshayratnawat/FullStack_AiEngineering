"""Who am I? Lets the browser check, right after sign-in, that this account may use the app."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, get_current_user

router = APIRouter()


class AccountOut(BaseModel):
    id: UUID
    email: str


@router.get("/me")
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> AccountOut:
    # get_current_user has already refused (403) an address outside the allowed domains,
    # or one not confirmed yet, so reaching here means the account may use the app.
    return AccountOut(id=user.id, email=user.email)
