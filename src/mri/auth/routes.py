"""Auth API routes — login, logout, whoami, change password.

Single-user model: there's exactly ONE admin. Login is required for
all dashboard endpoints. CLI does NOT require login (it runs locally
with the same DB, so it has direct access).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from mri.auth.users import (
    change_password as change_password_db,
)
from mri.auth.users import (
    count_users,
    create_token,
    get_user_by_id,
    get_user_by_username,
    record_login,
    verify_password,
    verify_token,
)
from mri.config import get_config
from mri.security import sanitize_for_log

logger = logging.getLogger("mri.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


# Optional bearer auth — depends on whether MRI_API_KEYS env is set
# We use JWT instead of API keys; the legacy env-based key still works
# for backwards compatibility (one key = bypass JWT).
from mri.security import check_api_key as _legacy_check_api_key  # noqa: E402

bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=1, max_length=200)


class LoginResponse(BaseModel):
    token: str
    user: dict
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=200)


class WhoAmIResponse(BaseModel):
    id: int
    username: str
    created_at: str
    last_login_at: str | None


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def require_user(
    request: Request,
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """FastAPI dependency: require a valid JWT, return user record.

    Legacy API keys (MRI_API_KEYS env) still work as a bypass for
    backwards compatibility and CLI usage.
    """
    # 1. Try JWT in Authorization header
    if bearer_creds is not None and bearer_creds.scheme.lower() == "bearer":
        token = bearer_creds.credentials
        # JWTs always have 3 dot-separated parts — if the token doesn't look
        # like a JWT, check if it's a legacy API key (only when configured).
        if token.count(".") == 2:
            # Looks like a JWT — verify as such
            claims = verify_token(token)
            if claims is not None:
                user = get_user_by_id(int(claims["sub"]))
                if user is not None:
                    return user
        else:
            # Not a JWT — try legacy API key
            if _legacy_check_api_key(token):
                return {
                    "id": 0,
                    "username": "api-key",
                    "legacy": True,
                }
    # 2. Try session cookie
    cookie_name = get_config().get("auth", {}).get("session_cookie_name", "mri_session")
    token = request.cookies.get(cookie_name)
    if token:
        claims = verify_token(token)
        if claims is not None:
            user = get_user_by_id(int(claims["sub"]))
            if user is not None:
                return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


# A bcrypt hash of a random throwaway value, at the same cost as real hashes.
# Verified against when the username is unknown, so login takes the same time
# whether or not the account exists. Not a secret and not a usable credential.
_ENUMERATION_GUARD_HASH = "$2b$12$wdS/fZRSjLLsPaX2fgNkUOVYYYlHiaa2JlEM4QxoMVMMstyK7Bm1G"


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, response: Response) -> LoginResponse:
    """Authenticate with username + password, get a JWT."""
    # bcrypt at cost 12 is ~195 ms of deliberate CPU, and each of these helpers
    # also opens SQLite synchronously. Run on a worker thread: otherwise one
    # login freezes every other request and WebSocket on the server for the
    # duration.
    user = await asyncio.to_thread(get_user_by_username, req.username)
    # Always run a verification, even for an unknown username. Short-circuiting
    # returned in microseconds for a user that does not exist and ~195 ms for one
    # that does, which is a timing oracle for username enumeration — exactly what
    # the generic error message below is meant to prevent.
    stored_hash = user["password_hash"] if user is not None else _ENUMERATION_GUARD_HASH
    password_ok = await asyncio.to_thread(verify_password, req.password, stored_hash)
    if user is None or not password_ok:
        logger.info(
            "auth.login.failed",
            extra={"event": "auth.login.failed", "username": sanitize_for_log(req.username)},
        )
        # Generic error to avoid username enumeration
        raise HTTPException(status_code=401, detail="Invalid username or password")
    await asyncio.to_thread(record_login, user["id"])
    cfg = get_config().get("auth", {})
    ttl = int(cfg.get("jwt_ttl_seconds", 86400))
    token = await asyncio.to_thread(
        create_token, user["id"], user["username"], ttl_seconds=ttl
    )
    cookie_name = cfg.get("session_cookie_name", "mri_session")
    response.set_cookie(
        key=cookie_name,
        value=token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        # secure=True in production (HTTPS only) — can be set via env later
    )
    logger.info(
        "auth.login.ok",
        extra={"event": "auth.login.ok", "user_id": user["id"]},
    )
    return LoginResponse(
        token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "created_at": user["created_at"],
            "last_login_at": user["last_login_at"],
        },
        expires_in=ttl,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the session cookie."""
    cookie_name = get_config().get("auth", {}).get("session_cookie_name", "mri_session")
    response.delete_cookie(cookie_name)
    return {"ok": True}


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(user: dict = Depends(require_user)) -> WhoAmIResponse:
    """Return the current authenticated user."""
    return WhoAmIResponse(
        id=user["id"],
        username=user["username"],
        created_at=user.get("created_at", ""),
        last_login_at=user.get("last_login_at"),
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(require_user),
) -> dict:
    """Change the current user's password."""
    if user.get("legacy"):
        raise HTTPException(403, "Cannot change password for legacy API key user")
    # Same reasoning as login: bcrypt plus a synchronous SQLite open would
    # otherwise stall the whole server for the duration.
    full = await asyncio.to_thread(get_user_by_id, user["id"])
    if full is None or not await asyncio.to_thread(
        verify_password, req.current_password, full["password_hash"]
    ):
        raise HTTPException(401, "Current password is incorrect")
    if req.new_password == req.current_password:
        raise HTTPException(400, "New password must differ from current")
    await asyncio.to_thread(change_password_db, user["id"], req.new_password)
    logger.info(
        "auth.password.changed",
        extra={"event": "auth.password.changed", "user_id": user["id"]},
    )
    return {"ok": True}


@router.get("/status")
async def auth_status() -> dict:
    """Public — check whether the install is initialized.

    Returns `{"initialized": bool, "user_count": int}`.
    """
    return {
        "initialized": count_users() > 0,
        "user_count": count_users(),
    }


__all__ = ["router", "require_user"]
