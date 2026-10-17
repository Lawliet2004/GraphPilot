"""Per-user BYOK provider credentials, encrypted with the durable credential key.

Secret material exists only inside Fernet ciphertext at rest and inside the
provider request headers at call time. Keys are never serialized, logged,
returned with a suffix, or reachable through the graph/conversation payloads.
"""

import re

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete as sql_delete

from api.config import settings
from api.db import utcnow
from api.models import ModelCredential

# Users choose a provider, never a URL. Endpoints are fixed HTTPS origins so no
# request can be steered to an arbitrary host (SSRF) by credential data.
PROVIDERS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

# Provider model IDs only (e.g. "openai/gpt-4o-mini", "gpt-4o-mini"). Anything
# else is rejected before it can reach a request body.
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}")


def cipher():
    if not settings().credential_key:
        raise HTTPException(503, "Credential encryption is not configured on this server")
    return Fernet(settings().credential_key.encode())


def seal(value):
    return cipher().encrypt(value.encode()).decode()


def unseal(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(
            503,
            "Stored model credentials could not be decrypted. Update or remove them in Settings.",
        ) from None


def status_for(db, user_id):
    """Public status shape. It deliberately contains no key material or suffix."""
    row = db.get(ModelCredential, user_id)
    return {
        "configured": bool(row),
        "provider": row.provider if row else None,
        "model": row.model if row else None,
        "updated_at": row.updated_at if row else None,
        "byok_available": bool(settings().credential_key),
        "providers": sorted(PROVIDERS),
    }


def save(db, user_id, provider, model, api_key):
    row = db.get(ModelCredential, user_id)
    if row is None:
        row = ModelCredential(user_id=user_id)
        db.add(row)
    row.provider = provider
    row.model = model
    row.api_key = seal(api_key)
    row.updated_at = utcnow()


def delete(db, user_id):
    db.execute(sql_delete(ModelCredential).where(ModelCredential.user_id == user_id))


def for_synthesis(db, user_id):
    """Resolve the decrypted credential for one provider call, or None.

    Callers must pass the result straight to synthesis; it is never stored.
    Unusable ciphertext (rotated/missing key, tampering) degrades to None so
    graph-only answers keep working; the user repairs via Settings save/delete.
    """
    row = db.get(ModelCredential, user_id)
    if not row:
        return None
    try:
        key = unseal(row.api_key)
    except HTTPException:
        return None
    return {
        "provider": row.provider,
        "model": row.model,
        "api_key": key,
    }
