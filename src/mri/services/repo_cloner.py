"""Repository cloning — supports GitHub, GitLab, Bitbucket, generic git URLs.

When a user passes a URL to `mri scan` or POST /api/scans, we:
  1. Parse the URL to identify the host (github.com, gitlab.com, etc.)
  2. Choose an auth strategy based on the host + the configured integrations
  3. Shallow-clone to a local cache directory
  4. Track the clone in the DB so we can re-scan it without re-downloading
  5. Optionally clean up the clone after the scan (config: `clones.auto_cleanup`)

Clones are stored in `~/.cache/project-mri/repos/<hash-of-url>/`. The hash
prevents path collisions and makes it easy to identify a clone by its URL.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import shutil
import socket
import stat
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mri.config import get_config
from mri.db.repository import default_db_path

logger = logging.getLogger("mri.cloner")

# Hosts we allow cloning from by default. Extend via `clones.allowed_hosts`
# in config, or the configured self-hosted GitLab URL. This is the primary
# guard against SSRF / cloning from arbitrary or internal endpoints.
_DEFAULT_ALLOWED_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")

# Sandbox quotas. Fallbacks used only when a config value is absent; the merged
# config normally supplies these from `clones.*` (see config._DEFAULT_CONFIG).
# A depth of 0 (or a falsy value) means "full history"; a cap of 0 disables it.
_DEFAULT_CLONE_DEPTH = 50  # shallow-clone depth when the caller passes none
_DEFAULT_MAX_CLONE_BYTES = 524_288_000  # 500 MiB
_DEFAULT_MAX_CLONE_FILES = 50_000


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

class RepoUrl:
    """A parsed remote repo URL."""

    def __init__(self, raw: str, host: str, owner: str, name: str, scheme: str = "https"):
        self.raw = raw
        self.host = host.lower()
        self.owner = owner
        self.name = name
        self.scheme = scheme

    @property
    def display(self) -> str:
        return f"{self.host}/{self.owner}/{self.name}"

    @property
    def canonical_url(self) -> str:
        return f"{self.scheme}://{self.host}/{self.owner}/{self.name}.git"

    def __repr__(self) -> str:
        return f"RepoUrl({self.display})"


def parse_repo_url(url: str) -> RepoUrl:
    """Parse a git URL into RepoUrl.

    Supports:
    - https://github.com/owner/name
    - https://github.com/owner/name.git
    - git@github.com:owner/name.git (SSH form)
    - https://gitlab.com/group/subgroup/name
    """
    url = url.strip()
    if not url:
        raise ValueError("empty URL")

    # SSH form: git@host:owner/name.git
    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", url)
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"cannot parse SSH URL: {url}")
        owner = "/".join(parts[:-1])
        name = parts[-1]
        return RepoUrl(url, host, owner, name, scheme="ssh")

    # HTTPS / HTTP form
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http", "git"):
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError(f"URL missing host: {url}")
    path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"URL path should be owner/name: {url}")
    owner = "/".join(parts[:-1])
    name = parts[-1]
    return RepoUrl(url, parsed.netloc, owner, name, scheme=parsed.scheme)


# ---------------------------------------------------------------------------
# Auth strategies
# ---------------------------------------------------------------------------


def _build_authenticated_url(repo: RepoUrl, config: dict) -> str:
    """Inject credentials into the URL for HTTPS-based cloning.

    Returns a URL with basic auth embedded. Caller is responsible for
    passing the result to git CLI (which will use it once and discard).
    Never log this URL.
    """
    integrations = config.get("integrations", {})
    host_config = integrations.get(repo.host, {}) or integrations.get(_host_alias(repo.host), {})

    # Try host-specific token
    token = host_config.get("token") if isinstance(host_config, dict) else None

    # Also check the generic "github" / "gitlab" keys
    if not token:
        if "github.com" in repo.host and "github" in integrations:
            token = integrations["github"].get("token")
        elif "gitlab" in repo.host and "gitlab" in integrations:
            token = integrations["gitlab"].get("token")

    if not token:
        return repo.canonical_url

    # Embed token in URL
    from urllib.parse import quote
    auth = quote(token, safe="")
    # https://x-access-token:TOKEN@github.com/owner/name.git
    return f"https://x-access-token:{auth}@{repo.host}/{repo.owner}/{repo.name}.git"


def _host_alias(host: str) -> str:
    """Map a host to its config key (e.g. www.github.com -> github)."""
    host = host.lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if "bitbucket" in host:
        return "bitbucket"
    return host


# ---------------------------------------------------------------------------
# Clone cache
# ---------------------------------------------------------------------------


def _default_cache_dir() -> Path:
    config = get_config()
    cache = config.get("clones", {}).get("cache_dir")
    if cache:
        return Path(cache).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "project-mri" / "repos"


def _url_to_cache_path(url: str, cache_dir: Path) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return cache_dir / h


def is_cached(url: str) -> bool:
    """Return True if this URL has been cloned before."""
    cache_dir = _default_cache_dir()
    path = _url_to_cache_path(url, cache_dir)
    return path.exists() and (path / ".git").exists()


def _record_clone(url: str, local_path: Path, default_branch: str | None = None) -> None:
    """Upsert the cloned_repos row using a synchronous sqlite3 connection.

    clone_repo runs inside ``asyncio.to_thread`` (no event loop in this worker
    thread), so the async ``get_connection`` context manager cannot be used
    here. We open a short-lived sync sqlite3 connection instead, mirroring the
    pattern in ``services/webhook.py``. The schema is brought up to date first so
    the row persists even on the CLI ``mri scan <url>`` path.
    """
    from mri.db.migrator import migrate
    from mri.db.repository import connect_sync

    now = datetime.now(timezone.utc).isoformat()
    db_path = default_db_path()
    migrate(db_path)
    conn = connect_sync(db_path)
    try:
        conn.execute(
            """
            INSERT INTO cloned_repos (url, local_path, default_branch, last_scanned_at, scan_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(url) DO UPDATE SET
                local_path = excluded.local_path,
                default_branch = COALESCE(excluded.default_branch, cloned_repos.default_branch),
                last_scanned_at = excluded.last_scanned_at,
                scan_count = cloned_repos.scan_count + 1
            """,
            (url, str(local_path), default_branch, now),
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Clone-target validation (allowlist + SSRF guard)
# ---------------------------------------------------------------------------


def _allowed_hosts(config: dict) -> set[str]:
    hosts = {h.lower() for h in _DEFAULT_ALLOWED_HOSTS}
    clones = config.get("clones", {}) or {}
    for h in clones.get("allowed_hosts", []) or []:
        hosts.add(str(h).strip().lower())
    # A configured self-hosted GitLab counts as allowed.
    gitlab = (config.get("integrations", {}) or {}).get("gitlab", {}) or {}
    gl_url = gitlab.get("url")
    if gl_url:
        netloc = urlparse(gl_url).netloc.lower().split("@")[-1].split(":")[0]
        if netloc:
            hosts.add(netloc)
    return hosts


def _resolves_to_internal(hostname: str) -> bool:
    """True if the host resolves to (or is) a private/loopback/link-local/reserved IP.

    Defense-in-depth against SSRF and DNS-rebinding to internal endpoints such
    as the cloud metadata service (169.254.169.254).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return True  # cannot resolve -> refuse
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def _validate_clone_target(repo: RepoUrl, config: dict) -> None:
    """Reject clone targets that are not allow-listed or resolve internally."""
    hostname = repo.host.split("@")[-1].split(":")[0].lower()
    allowed = _allowed_hosts(config)
    if hostname not in allowed:
        raise CloneError(
            f"host '{hostname}' is not permitted for cloning. "
            f"Allowed: {sorted(allowed)}. Add it under clones.allowed_hosts to permit it."
        )
    if _resolves_to_internal(hostname):
        raise CloneError(
            f"refusing to clone from '{hostname}': it resolves to a private, "
            "loopback, or link-local address."
        )


# ---------------------------------------------------------------------------
# Sandbox quotas (on-disk size / file-count caps)
# ---------------------------------------------------------------------------


def _robust_rmtree(path: Path) -> None:
    """Delete a tree even when it holds read-only files.

    Git marks pack files inside `.git` read-only, and on Windows ``os.remove``
    refuses to unlink a read-only file — so ``shutil.rmtree(ignore_errors=True)``
    silently leaves a rejected clone on disk, defeating the fail-closed guarantee.
    This retries each failed entry after clearing the read-only bit.
    """
    def _clear_readonly(func: Any, target: str, _exc: Any) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass  # best effort; the CloneError still surfaces to the caller

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly)
    else:  # pragma: no cover - onerror is removed in 3.14+; kept for older runtimes
        shutil.rmtree(
            path,
            onerror=lambda func, target, _exc: _clear_readonly(func, target, None),
        )


def _clone_quota(config: dict) -> tuple[int, int]:
    """Return the (max_bytes, max_files) caps for a single clone.

    Read from `clones.max_clone_bytes` / `clones.max_clone_files`, falling back
    to the module defaults when a key is absent. A value of 0 disables that cap.
    """
    clones = config.get("clones", {}) or {}
    max_bytes = clones.get("max_clone_bytes", _DEFAULT_MAX_CLONE_BYTES)
    max_files = clones.get("max_clone_files", _DEFAULT_MAX_CLONE_FILES)
    return int(max_bytes), int(max_files)


def _directory_stats(path: Path) -> tuple[int, int]:
    """Return (total_bytes, file_count) for everything under `path`.

    Counts the whole on-disk footprint, including `.git`, because that is the
    disk a hostile repo actually consumes. Symlinked directories are not
    descended into (``os.walk`` default), so this cannot be sent into a loop.
    """
    total_bytes = 0
    file_count = 0
    for root, _dirs, files in os.walk(path):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                total_bytes += os.path.getsize(fpath)
            except OSError:
                # A vanished/unreadable entry still counts toward the file cap.
                pass
            file_count += 1
    return total_bytes, file_count


def _enforce_clone_quota(local_path: Path, config: dict) -> None:
    """Fail closed if the clone at `local_path` exceeds its size/file caps.

    Enforced *after* the clone lands: git offers no reliable hard byte cap
    mid-clone (``--filter`` shapes a partial clone but does not abort on a
    threshold), so the honest control is to measure the result and, if it is
    over budget, delete it and raise. A rejected clone must not be left on disk.
    """
    max_bytes, max_files = _clone_quota(config)
    if max_bytes <= 0 and max_files <= 0:
        return  # both caps disabled
    total_bytes, file_count = _directory_stats(local_path)
    reason: str | None = None
    if max_bytes > 0 and total_bytes > max_bytes:
        reason = f"on-disk size {total_bytes} bytes exceeds cap of {max_bytes} bytes"
    elif max_files > 0 and file_count > max_files:
        reason = f"file count {file_count} exceeds cap of {max_files} files"
    if reason is not None:
        _robust_rmtree(local_path)
        logger.error(
            "clone.quota_exceeded",
            extra={
                "event": "clone.quota_exceeded",
                "path": str(local_path),
                "reason": reason,
            },
        )
        raise CloneError(
            f"cloned repository rejected: {reason}. The partial clone was deleted."
        )


# ---------------------------------------------------------------------------
# Clone operation
# ---------------------------------------------------------------------------


class CloneError(Exception):
    """Raised when cloning fails."""


def clone_repo(
    url: str,
    *,
    branch: str | None = None,
    depth: int | None = None,
    force_refresh: bool = False,
) -> Path:
    """Clone a remote repo to local cache, returning the local path.

    Args:
        url: remote git URL (https or SSH)
        branch: branch to clone (defaults to repo's default)
        depth: shallow clone depth (1 = latest only). None applies the
            configured shallow default (`clones.default_depth`, 50) so a huge
            repo's whole history is not fetched by accident; pass 0 for full
            history.
        force_refresh: if True, delete cached clone and re-clone

    Returns:
        Local filesystem path to the cloned repo.

    Raises:
        CloneError: on any failure
    """
    config = get_config()
    repo = parse_repo_url(url)
    _validate_clone_target(repo, config)
    # Resolve the effective depth: None -> configured shallow default so we never
    # silently fetch full history; 0 (or any falsy override) -> full history.
    if depth is None:
        depth = int((config.get("clones", {}) or {}).get("default_depth", _DEFAULT_CLONE_DEPTH))
    cache_dir = _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_path = _url_to_cache_path(url, cache_dir)

    # Update existing clone
    if local_path.exists() and (local_path / ".git").exists() and not force_refresh:
        try:
            # `git fetch` updates refs but never touches the working tree. The
            # analyzers walk files on disk, so without an explicit checkout a
            # re-scan would analyse whatever branch happened to be checked out
            # last while the report claimed the requested one — a silently wrong
            # answer. FETCH_HEAD is used rather than origin/<branch> because it
            # is what a shallow fetch reliably sets.
            if branch:
                _run_git("fetch", "--depth", str(depth or 1), "origin", branch, cwd=local_path)
                _run_git("checkout", "-B", branch, "FETCH_HEAD", cwd=local_path)
            else:
                _run_git("fetch", "--depth", str(depth or 1), "origin", cwd=local_path)
                _run_git("reset", "--hard", "FETCH_HEAD", cwd=local_path)
        except CloneError:
            # Update failed — fall through to fresh clone
            shutil.rmtree(local_path, ignore_errors=True)
        else:
            # Quota check on the else branch (not inside the try): a quota
            # rejection must propagate to the caller, not trigger a full
            # re-clone that would only exceed the same cap again.
            _enforce_clone_quota(local_path, config)
            _record_clone(url, local_path)
            logger.info(
                "clone.updated",
                extra={"event": "clone.updated", "url": url, "path": str(local_path)},
            )
            return local_path

    # Fresh clone
    if local_path.exists():
        shutil.rmtree(local_path, ignore_errors=True)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    auth_url = _build_authenticated_url(repo, config)
    # _run_git prepends "git" itself — including it here produced `git git clone`,
    # which failed every fresh clone.
    cmd = ["clone"]
    if depth:
        cmd += ["--depth", str(depth)]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_url, str(local_path)]

    logger.info(
        "clone.start",
        extra={
            "event": "clone.start",
            "url": url,
            "host": repo.host,
            "owner": repo.owner,
            # Not "name": that is a reserved LogRecord attribute and logging
            # raises KeyError when `extra` tries to overwrite it, which turned a
            # successful clone into a crash whenever INFO logging was enabled.
            "repo_name": repo.name,
            "branch": branch or "(default)",
            "depth": depth or "(full)",
        },
    )
    try:
        _run_git(*cmd, timeout=300)  # 5min timeout for clones
    except CloneError as e:
        # Never log the auth_url (it has the token)
        logger.error(
            "clone.failed",
            extra={"event": "clone.failed", "url": url, "error": str(e)},
        )
        raise

    # Fail closed if the freshly cloned repo blows past its size/file caps.
    _enforce_clone_quota(local_path, config)

    # Detect default branch if not specified
    if not branch:
        try:
            branch = _run_git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=local_path
            ).strip()
        except CloneError:
            branch = "main"

    # Update DB record (sync sqlite3 — see _record_clone docstring)
    _record_clone(url, local_path, branch)

    logger.info(
        "clone.done",
        extra={
            "event": "clone.done",
            "url": url,
            "path": str(local_path),
            "branch": branch,
        },
    )
    return local_path


def cleanup_clone(url: str) -> None:
    """Remove a cached clone (if `clones.keep_clones` is False, this runs after each scan)."""
    config = get_config()
    if config.get("clones", {}).get("keep_clones", False):
        return
    cache_dir = _default_cache_dir()
    local_path = _url_to_cache_path(url, cache_dir)
    if local_path.exists():
        shutil.rmtree(local_path, ignore_errors=True)
        logger.info(
            "clone.cleaned",
            extra={"event": "clone.cleaned", "url": url},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_git(*args: Any, cwd: Path | str | None = None, timeout: int = 60) -> str:
    """Run a git command, return stdout. Raise CloneError on non-zero exit."""
    cmd = ["git", *args]
    # Never let git block on an interactive credential/host prompt: a private
    # URL with no configured token must fail fast instead of hanging a worker.
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
    }
    try:
        result = subprocess.run(  # nosec B603  # fixed args, no shell, URL-validated
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise CloneError(f"git command timed out after {timeout}s: {' '.join(cmd[:3])}…") from e
    except FileNotFoundError as e:
        raise CloneError("git is not installed or not in PATH") from e
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:500]
        raise CloneError(f"git {args[0] if args else '?'} failed: {stderr}") from None
    return result.stdout


__all__ = [
    "RepoUrl",
    "parse_repo_url",
    "clone_repo",
    "cleanup_clone",
    "is_cached",
    "CloneError",
]
