"""Single-user auth for self-hosted MRI.

There is exactly ONE admin user per installation. They are created
during `mri init` and own everything. No public registration, no
multi-tenant — this is a self-hosted tool.

Storage: SQLite (in the same DB as scans).

Password hashing: bcrypt (cost 12).
Sessions: JWT (HS256) with 24h expiry, secret stored in DB.
"""
from __future__ import annotations

import secrets
import sqlite3
import time
from typing import Any

import bcrypt
import jwt

# ---------------------------------------------------------------------------
# Sync DB connection (auth users can be created/synced from CLI which is sync)
# ---------------------------------------------------------------------------

def _sync_conn() -> sqlite3.Connection:
    """Open a synchronous sqlite3 connection with the schema up to date."""
    from mri.db.migrator import migrate
    from mri.db.repository import default_db_path

    db_path = default_db_path()
    migrate(db_path)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt. Returns the encoded hash as a string."""
    if not plain or len(plain) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check that `plain` matches `hashed`."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

JWT_ALG = "HS256"
JWT_ISSUER = "project-mri"
JWT_AUDIENCE = "project-mri-dashboard"


def _load_or_create_jwt_secret(conn: sqlite3.Connection) -> str:
    """Load JWT secret from app_settings table, creating one if missing."""
    row = conn.execute("SELECT value FROM app_settings WHERE key = 'jwt_secret'").fetchone()
    if row is not None:
        return row[0]
    secret = secrets.token_urlsafe(48)
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
        ("jwt_secret", secret),
    )
    conn.commit()
    return secret


def create_token(user_id: int, username: str, *, ttl_seconds: int = 86400) -> str:
    """Create a signed JWT for the given user."""
    conn = _sync_conn()
    try:
        secret = _load_or_create_jwt_secret(conn)
    finally:
        conn.close()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALG)


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a JWT, returning the claims if valid, None if not."""
    if not token:
        return None
    conn = _sync_conn()
    try:
        secret = _load_or_create_jwt_secret(conn)
    finally:
        conn.close()
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALG],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


def get_user_by_username(username: str) -> dict | None:
    """Return user record by username, or None."""
    conn = _sync_conn()
    try:
        cur = conn.execute(
            "SELECT id, username, password_hash, created_at, last_login_at FROM users WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3],
            "last_login_at": row[4],
        }
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Return user record by id, or None."""
    conn = _sync_conn()
    try:
        cur = conn.execute(
            "SELECT id, username, password_hash, created_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "created_at": row[3],
            "last_login_at": row[4],
        }
    finally:
        conn.close()


def create_user(username: str, password: str) -> dict:
    """Create a new user. Raises ValueError if user already exists or password is too weak."""
    if not username or len(username) < 3:
        raise ValueError("username must be at least 3 characters")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("username may only contain letters, numbers, underscore, hyphen")
    if get_user_by_username(username) is not None:
        raise ValueError(f"user '{username}' already exists")
    pw_hash = hash_password(password)
    conn = _sync_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, pw_hash),
        )
        conn.commit()
        return {"id": int(cur.lastrowid or 0), "username": username}
    finally:
        conn.close()


def change_password(user_id: int, new_password: str) -> None:
    """Change a user's password. Validates strength."""
    pw_hash = hash_password(new_password)
    conn = _sync_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (pw_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def record_login(user_id: int) -> None:
    """Update last_login_at timestamp for a user."""
    conn = _sync_conn()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = datetime('now') WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def count_users() -> int:
    """Return number of users. Used to detect first-run state."""
    conn = _sync_conn()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0] or 0)
    finally:
        conn.close()


__all__ = [
    "hash_password",
    "verify_password",
    "create_token",
    "verify_token",
    "get_user_by_username",
    "get_user_by_id",
    "create_user",
    "change_password",
    "record_login",
    "count_users",
]
