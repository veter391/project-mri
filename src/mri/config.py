"""Configuration loader for .mri.yml.

Configuration is loaded from the first file found in this order:
1. Path specified in MRI_CONFIG env var
2. ./.mri.yml (current directory)
3. ~/.config/project-mri/config.yml
4. /etc/project-mri/config.yml

Most fields are optional — sensible defaults are used. The only required
fields are set during `mri init` (admin user credentials).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 7331,
        "log_format": "text",  # or "json" for production
        "log_level": "INFO",
        "cors_origins": [],  # deny by default; set in prod
        "rate_limit_per_min": 60,
        "scan_rate_limit_per_min": 5,
        "max_request_bytes": 1048576,  # 1 MiB
    },
    "database": {
        "path": None,  # uses MRI_DB env, or default ~/.cache/project-mri/mri.db
    },
    "scans": {
        "default_branch": "main",
        "max_concurrent": 3,
        "timeout_seconds": 3600,
        "exclude_globs": [
            "**/.git/**",
            "**/node_modules/**",
            "**/vendor/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**",
            "**/.venv/**",
            "**/venv/**",
            "**/.mypy_cache/**",
            "**/.pytest_cache/**",
        ],
        "include_globs": None,  # None = all
    },
    "analyzers": {
        "git_history": {"enabled": True, "max_commits": 10000},
        "architecture": {"enabled": True},
        "dependencies": {"enabled": True},
        "complexity": {"enabled": True, "max_file_bytes": 2_000_000},
        "tech_debt": {"enabled": True, "max_file_bytes": 1_000_000},
        "coupling": {"enabled": True},
    },
    "auth": {  # nosec B105  # placeholder, not a password
        "jwt_secret": "",  # auto-generated on first run, stored in DB  # nosec B105
        "jwt_ttl_seconds": 86400,  # 24h
        "session_cookie_name": "mri_session",
    },
    "integrations": {  # nosec B105
        "github": {"token": ""},  # nosec B105
        "gitlab": {"token": "", "url": "https://gitlab.com"},  # nosec B105
    },
    "notifications": {  # nosec B105
        "webhook": {
            "url": "",
            "events": ["scan_complete", "scan_failed"],
        },
    },
    "clones": {
        "cache_dir": None,  # ~/.cache/project-mri/repos
        "auto_cleanup": True,
        "keep_clones": False,  # delete clones after scan
    },
    "watch": {
        "debounce_seconds": 2.0,
        "ignore_globs": ["**/.git/**", "**/node_modules/**"],
    },
    "dashboard": {
        "theme": "auto",  # auto, dark, light
        "items_per_page": 25,
    },
}


def _search_order() -> list[Path]:
    """Every location the loader considers, whether or not it exists."""
    paths: list[Path] = []
    env = os.environ.get("MRI_CONFIG")
    if env:
        paths.append(Path(env))
    paths.append(Path.cwd() / ".mri.yml")
    paths.append(Path.cwd() / "config.yml")
    paths.append(Path.home() / ".config" / "project-mri" / "config.yml")
    paths.append(Path("/etc/project-mri/config.yml"))
    return paths


def _candidate_config_paths() -> list[Path]:
    """Return the config file search paths in priority order."""
    return [p for p in _search_order() if p.exists()]


def is_discoverable(path: Path) -> bool:
    """True if the loader would actually pick this file up.

    Used by `mri init` so that writing a config to a custom location reports
    honestly: the file gets created either way, but outside the search order
    nothing ever reads it.
    """
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    for candidate in _search_order():
        try:
            if candidate.expanduser().resolve() == resolved:
                return True
        except OSError:
            continue
    return False


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict.

    Sub-dicts are merged, lists are replaced, scalars are replaced.
    """
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config from disk, falling back to defaults.

    Args:
        path: explicit config file. If None, searches standard locations.

    Raises:
        FileNotFoundError: if `path` is provided but the file doesn't exist.
    """
    if path is not None:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with config_path.open("r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        return _deep_merge(_DEFAULT_CONFIG, user_config)
    for candidate in _candidate_config_paths():
        try:
            with candidate.open("r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            return _deep_merge(_DEFAULT_CONFIG, user_config)
        except (OSError, yaml.YAMLError):
            continue
    return dict(_DEFAULT_CONFIG)


def write_default_config(path: Path) -> None:
    """Write a commented default config to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# project-mri configuration\n")
        f.write("# Generated by `mri init` — edit as needed.\n")
        f.write("# Docs: https://github.com/project-mri/project-mri/blob/main/docs/CONFIG.md\n\n")
        yaml.safe_dump(_DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)


# Singleton loaded on first access
_config: dict[str, Any] | None = None


def get_config(reload: bool = False) -> dict[str, Any]:
    """Return the cached config, loading on first call."""
    global _config
    if _config is None or reload:
        _config = load_config()
    return _config


__all__ = [
    "load_config",
    "write_default_config",
    "get_config",
    "_DEFAULT_CONFIG",
]
