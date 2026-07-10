"""Security helpers — path validation, input sanitization, API keys.

Centralised so we have ONE place to audit for security regressions.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (env-driven)
# ---------------------------------------------------------------------------

# Comma-separated list of allowed roots for project_path.
# Empty list = allow any path (development only).
ALLOWED_ROOTS_ENV = "MRI_ALLOWED_ROOTS"
# API key(s). Comma-separated. Empty = auth disabled (development only).
API_KEYS_ENV = "MRI_API_KEYS"
# Allowed CORS origins. Empty = deny CORS entirely.
CORS_ORIGINS_ENV = "MRI_CORS_ORIGINS"
# Max request size in bytes (default 1 MiB).
MAX_REQUEST_BYTES_ENV = "MRI_MAX_REQUEST_BYTES"


def get_allowed_roots() -> list[Path]:
    """Return the list of allowed roots for project_path, or [] for unrestricted."""
    raw = os.environ.get(ALLOWED_ROOTS_ENV, "").strip()
    if not raw:
        return []
    return [Path(p).expanduser().resolve() for p in raw.split(",") if p.strip()]


def get_api_keys() -> set[str]:
    """Return the set of valid API keys, or empty set for no-auth mode."""
    raw = os.environ.get(API_KEYS_ENV, "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def get_cors_origins() -> list[str]:
    """Return the allowed CORS origins, or [] to disable CORS."""
    raw = os.environ.get(CORS_ORIGINS_ENV, "").strip()
    if not raw:
        # Special: "*" is allowed but dangerous. Refuse by default.
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_max_request_bytes() -> int:
    raw = os.environ.get(MAX_REQUEST_BYTES_ENV, "").strip()
    try:
        return int(raw) if raw else 1024 * 1024  # 1 MiB default
    except ValueError:
        return 1024 * 1024


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


class PathValidationError(ValueError):
    """Raised when a project path is rejected."""


def validate_project_path(raw_path: str) -> Path:
    """Validate a project path against the allowlist.

    Raises PathValidationError if:
    - Path is empty
    - Path doesn't exist
    - Path isn't a directory
    - Path isn't under any allowed root (when allowlist is configured)
    - Path tries to escape via '..'
    - Path is a symlink loop or unwritable

    Returns resolved absolute Path on success.
    """
    if not raw_path or not isinstance(raw_path, str):
        raise PathValidationError("project_path must be a non-empty string")

    s = raw_path.strip()
    if not s:
        raise PathValidationError("project_path cannot be empty")

    # Reject paths with NUL bytes (filesystem injection)
    if "\x00" in s:
        raise PathValidationError("project_path contains invalid characters")

    # Length cap (filesystem path limits)
    if len(s) > 4096:
        raise PathValidationError("project_path too long")

    # Resolve symlinks + '..'
    try:
        resolved = Path(s).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise PathValidationError(f"cannot resolve path: {e}")

    # Must exist and be a directory
    if not resolved.exists():
        raise PathValidationError(f"path does not exist: {s}")
    if not resolved.is_dir():
        raise PathValidationError(f"path is not a directory: {s}")

    # Allowlist check (if configured)
    allowed = get_allowed_roots()
    if allowed:
        if not any(_is_under(resolved, root) for root in allowed):
            raise PathValidationError(
                f"path '{resolved}' is not under any allowed root "
                f"({', '.join(str(r) for r in allowed)})"
            )

    return resolved


def _is_under(path: Path, root: Path) -> bool:
    """Return True if `path` is `root` or a descendant of it."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------


def is_auth_enabled() -> bool:
    """Auth is enforced when API keys are configured OR a dashboard user exists.

    Checking only API keys (the previous behavior) meant an operator who ran
    `mri init` and relied on JWT login — but did not set MRI_API_KEYS — got a
    server that let every request through unauthenticated (critical when the
    server is reverse-proxied on loopback). A configured user must gate the API.
    """
    if get_api_keys():
        return True
    try:
        from mri.auth.users import count_users
        return count_users() > 0
    except Exception:
        # DB not initialised yet (pre-`mri init`) -> no user-based auth.
        return False


# Explicit, knowing override for running unauthenticated on a non-loopback
# interface (e.g. behind a trusted VPN/proxy that terminates auth).
ALLOW_INSECURE_ENV = "MRI_ALLOW_INSECURE"


def is_loopback_host(host: str) -> bool:
    """True if `host` is a loopback address / localhost."""
    h = (host or "").strip().lower()
    if h in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def assert_safe_bind(host: str, *, has_user_auth: bool = False) -> None:
    """Fail closed: refuse to serve on a non-loopback interface without auth.

    MRI is local-first; binding to 0.0.0.0 or a public IP without any
    authentication would expose scan/clone/delete endpoints to the network.
    Raises RuntimeError unless auth is configured (API keys or a dashboard
    user), the bind host is loopback, or the operator sets MRI_ALLOW_INSECURE=1.
    """
    if is_loopback_host(host):
        return
    if is_auth_enabled() or has_user_auth:
        return
    if os.environ.get(ALLOW_INSECURE_ENV, "").strip() in ("1", "true", "yes"):
        return
    raise RuntimeError(
        f"Refusing to bind to non-loopback host '{host}' without authentication. "
        f"Set {API_KEYS_ENV} (or create a dashboard user with `mri init`), bind to "
        f"127.0.0.1, or set {ALLOW_INSECURE_ENV}=1 if this host is on a trusted network."
    )


def check_api_key(provided: str | None) -> bool:
    """Return True if the provided key is valid (or auth disabled).

    Constant-time comparison to prevent timing attacks.
    """
    valid_keys = get_api_keys()
    if not valid_keys:
        return True  # Auth disabled in dev mode
    if not provided:
        return False
    # Constant-time compare against all valid keys
    for vk in valid_keys:
        if hmac.compare_digest(provided, vk):
            return True
    return False


def generate_api_key() -> str:
    """Generate a cryptographically random API key (32 bytes, URL-safe)."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Other input sanitization
# ---------------------------------------------------------------------------


# Branch names must match git refname rules (simplified).
BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]{1,256}$")


def validate_branch(branch: str | None) -> str | None:
    """Validate a git branch name, return cleaned or None."""
    if branch is None:
        return None
    s = branch.strip()
    if not s:
        return None
    if not BRANCH_NAME_RE.match(s):
        raise ValueError(f"invalid branch name: {s!r}")
    if s.startswith("/") or s.endswith("/") or s.startswith("-"):
        raise ValueError(f"invalid branch name: {s!r}")
    if ".." in s or "@{" in s or "\\" in s:
        raise ValueError(f"invalid branch name: {s!r}")
    return s


# Slug for demo URLs (matches slug re below)
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_slug(slug: str) -> str:
    """Validate a demo slug."""
    if not isinstance(slug, str):
        raise ValueError("slug must be a string")
    s = slug.strip()
    if not SLUG_RE.match(s):
        raise ValueError(f"invalid slug: {slug!r}")
    return s


def sanitize_for_log(s: str, max_len: int = 200) -> str:
    """Sanitize a string for safe logging (truncate, strip control chars)."""
    if not isinstance(s, str):
        s = str(s)
    # Strip control chars except common whitespace
    s = "".join(c for c in s if c == "\n" or c == "\t" or ord(c) >= 0x20)
    if len(s) > max_len:
        s = s[:max_len] + f"...[truncated {len(s) - max_len}]"
    return s


# ---------------------------------------------------------------------------
# Hash for sensitive comparisons (e.g. logging without leaking values)
# ---------------------------------------------------------------------------


def short_hash(value: str, length: int = 8) -> str:
    """Return a short hash of `value` suitable for logs."""
    h = hashlib.sha256(value.encode()).hexdigest()
    return h[:length]