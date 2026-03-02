import uuid

from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_api_key
from app.models.api_key import ApiKey


class AuthenticatedKey:
    """Represents a validated API key with its associated metadata."""

    def __init__(self, api_key: ApiKey):
        self.key_id = api_key.id
        self.org_id = api_key.org_id
        self.collection_id = api_key.collection_id
        self.scope = api_key.scope
        self.rate_limit = api_key.rate_limit

    def has_scope(self, required: str) -> bool:
        if self.scope == "master":
            return True
        return self.scope == required

    def can_access_collection(self, collection_id: uuid.UUID) -> bool:
        if self.scope == "master":
            return True
        return self.collection_id == collection_id


async def get_api_key(
    request: Request,
    authorization: str = Header(..., description="Bearer <api_key>"),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedKey:
    """Validate the Bearer token and return the authenticated key info."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid authorization header format. Expected: Bearer <api_key>"}},
        )

    raw_key = authorization[7:]
    key_hash = hash_api_key(raw_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired API key"}},
        )

    return AuthenticatedKey(api_key)


def require_scope(required_scope: str):
    """Dependency that checks the API key has the required scope."""

    async def check_scope(auth: AuthenticatedKey = Depends(get_api_key)):
        if not auth.has_scope(required_scope):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"API key lacks required scope: {required_scope}",
                    }
                },
            )
        return auth

    return check_scope
