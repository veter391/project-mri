"""project-mri — local-first codebase intelligence."""
from typing import Any

__all__ = ["__version__"]


def __getattr__(name: str) -> Any:
    """Resolve `__version__` on first access (PEP 562).

    The version comes from the installed distribution's metadata, which is the
    single source of truth — it used to be hardcoded in four modules that would
    have gone stale on the first release bumping only pyproject.toml. But
    `importlib.metadata` costs ~58 ms to import, and paying that at package
    import time put it on every `mri --help`, `--version` and shell completion.
    Deferring it means only the code that actually reads the version pays.
    """
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("project-mri")
        except PackageNotFoundError:  # running from a source tree without an install
            return "0.0.0+unknown"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
