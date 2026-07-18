"""project-mri — local-first codebase intelligence."""
from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the installed distribution's metadata, which comes
    # from pyproject.toml. The version used to be hardcoded in four modules,
    # which would silently go stale on the first release that bumped only
    # pyproject.
    __version__ = version("project-mri")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
