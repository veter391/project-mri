"""Watch mode — re-scan a directory whenever files change.

Usage:
    mri watch /path/to/repo
    mri watch --depth 2 /path/to/repo

Uses watchdog for cross-platform FS events. Debounces changes (default 2s)
so a `git pull` that touches 100 files only triggers one rescan.

The callback is called synchronously from a worker thread, so it can spawn
its own asyncio loop (the CLI does `asyncio.run` inside the rescan).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from mri.config import get_config

logger = logging.getLogger("mri.watcher")


class _Handler(FileSystemEventHandler):
    """watchdog handler that debounces and calls a callback."""

    def __init__(self, on_change: Callable[[], None], ignore_globs: list[str], debounce: float):
        self._on_change = on_change
        self._ignore_globs = ignore_globs
        self._debounce = debounce
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _should_ignore(self, path: str) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(path, g) for g in self._ignore_globs)

    def _trigger(self, path: str) -> None:
        if self._should_ignore(path):
            return
        with self._lock:
            # Cancel any pending callback
            if self._timer is not None:
                self._timer.cancel()
            # Schedule a new one
            self._timer = threading.Timer(self._debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        try:
            self._on_change()
        except Exception as e:  # nosem: bandit
            logger.error(
                "watch.rescan.failed",
                extra={"event": "watch.rescan.failed", "error": str(e)},
            )

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._trigger(event.dest_path)


class RepoWatcher:
    """Watch a directory and call a callback when files change (debounced).

    The callback runs in a worker thread after the debounce period.
    Use a thread-safe callback (e.g. one that spawns its own event loop).

    Usage:
        def rescan():
            asyncio.run(do_scan_async())

        watcher = RepoWatcher("/path/to/repo", on_change=rescan)
        watcher.start()      # blocks until stop() is called
        # ... in another thread or signal handler ...
        watcher.stop()
    """

    def __init__(
        self,
        path: str | Path,
        on_change: Callable[[], None],
        *,
        debounce_seconds: float | None = None,
        ignore_globs: list[str] | None = None,
    ):
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists() or not self.path.is_dir():
            raise ValueError(f"path does not exist or is not a directory: {self.path}")
        config = get_config()
        if debounce_seconds is None:
            debounce_seconds = config.get("watch", {}).get("debounce_seconds", 2.0)
        if ignore_globs is None:
            ignore_globs = config.get("watch", {}).get("ignore_globs", [])
        self.debounce_seconds = debounce_seconds
        self.ignore_globs = ignore_globs
        self._observer: BaseObserver | None = None
        self._on_change = on_change

    def start(self) -> None:
        """Start watching (synchronous, blocks the calling thread)."""
        if self._observer is not None:
            return
        handler = _Handler(self._on_change, self.ignore_globs, self.debounce_seconds)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.path), recursive=True)
        self._observer.start()
        logger.info(
            "watch.started",
            extra={"event": "watch.started", "path": str(self.path)},
        )

    def stop(self) -> None:
        """Stop watching."""
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        logger.info("watch.stopped", extra={"event": "watch.stopped"})


__all__ = ["RepoWatcher"]
