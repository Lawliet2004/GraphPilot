"""Per-user BYOK credential management. Browser sessions only.

CLI/agent bearer tokens are already refused by ``current_session`` for any path
outside its allowlist; the explicit browser check below keeps that guarantee if
the allowlist ever changes. CSRF is enforced there for every mutation too.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from api import model_credentials
from api.auth import audit, current_session
from api.db import db_session
from api.models import User

router = APIRouter(prefix="/api/model", tags=["model credentials"])


class CredentialBody(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    provider: Literal["openai", "openrouter"]
    model: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=10, max_length=256, repr=False)

    @field_validator("model")
    @classmethod
    def model_slug(cls, value):
        value = value.strip()
        if not model_credentials.MODEL_PATTERN.fullmatch(value):
            raise ValueError("Use a provider model ID such as openai/gpt-4o-mini")
        return value

    @field_validator("api_key")
    @classmethod
    def key_material(cls, value):
        if any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError("API keys cannot contain whitespace or control characters")
        return value


def browser_only(request: Request):
    if not getattr(request.state, "session", None):
        raise HTTPException(403, "Manage model credentials from a browser session")


@router.get("")
def status(user: User = Depends(current_session), db: Session = Depends(db_session)):
    return model_credentials.status_for(db, user.id)


@router.put("")
def save(
    body: CredentialBody,
    request: Request,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    browser_only(request)
    model_credentials.save(db, user.id, body.provider, body.model, body.api_key)
    audit(db, user.id, "model.saved", user.id, provider=body.provider, model=body.model)
    db.commit()
    return model_credentials.status_for(db, user.id)


@router.delete("")
def remove(
    request: Request,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    browser_only(request)
    model_credentials.delete(db, user.id)
    audit(db, user.id, "model.deleted", user.id)
    db.commit()
    return {"message": "Model credentials removed. Graph search remains available."}
