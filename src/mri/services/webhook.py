"""Webhook delivery — send HTTP POST on scan events.

Configurable via .mri.yml:
    notifications:
      webhook:
        url: https://your-server/webhook
        events: [scan_complete, scan_failed]

Deliveries are recorded in `webhook_deliveries` table for audit / retry.
Failed deliveries are kept for later inspection (not auto-retried in v1;
you can add retry logic via the CLI in a future iteration).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from mri.config import get_config

logger = logging.getLogger("mri.webhook")


async def send_webhook(
    event: str,
    payload: dict[str, Any],
    *,
    timeout: float = 10.0,
) -> int:
    """Send a webhook notification if configured for this event.

    Returns the delivery id (always, even if no webhook is configured).
    """
    config = get_config()
    webhook_cfg = config.get("notifications", {}).get("webhook", {}) or {}
    url = webhook_cfg.get("url")
    events = webhook_cfg.get("events", [])
    if not url or (events and event not in events):
        # No webhook configured for this event — record a "skipped" delivery
        async with _delivery_record(url or "(none)", event, payload, status_code=None, response_body="skipped (no config)"):
            pass
        return -1

    # Send the webhook
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "project-mri/0.3",
        "X-MRI-Event": event,
    }
    body = json.dumps(payload, default=str).encode("utf-8")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content=body, headers=headers)
        async with _delivery_record(url, event, payload, status_code=resp.status_code, response_body=resp.text[:1000]):
            pass
        if resp.status_code >= 400:
            logger.warning(
                "webhook.failed",
                extra={
                    "event": "webhook.failed",
                    "url": url,
                    "status": resp.status_code,
                    "scan_event": event,
                },
            )
        else:
            logger.info(
                "webhook.delivered",
                extra={
                    "event": "webhook.delivered",
                    "url": url,
                    "status": resp.status_code,
                    "scan_event": event,
                },
            )
        return resp.status_code
    except httpx.HTTPError as e:
        async with _delivery_record(url, event, payload, status_code=None, response_body=str(e)[:500]):
            pass
        logger.warning(
            "webhook.error",
            extra={
                "event": "webhook.error",
                "url": url,
                "error": str(e),
                "scan_event": event,
            },
        )
        return 0


class _delivery_record:
    """Async context manager to record a webhook delivery in the DB."""

    def __init__(self, url: str, event: str, payload: dict, *, status_code: int | None, response_body: str):
        self.url = url
        self.event = event
        self.payload = payload
        self.status_code = status_code
        self.response_body = response_body
        self._delivery_id: int | None = None

    async def __aenter__(self) -> _delivery_record:
        # Run the DB write in a thread to keep this async-safe.
        # We use sync sqlite3 here because aiosqlite's async connection
        # can't be entered from a worker thread (its event loop is bound
        # to the main loop). Sync sqlite3 is fine for this simple INSERT.
        def _insert() -> int:
            import sqlite3

            from mri.db.migrator import migrate
            from mri.db.repository import default_db_path

            db_path = default_db_path()
            migrate(db_path)
            conn = sqlite3.connect(str(db_path), isolation_level=None)
            try:
                cur = conn.execute(
                    """
                    INSERT INTO webhook_deliveries
                        (url, event, payload_json, status_code, response_body, delivered_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.url,
                        self.event,
                        json.dumps(self.payload, default=str),
                        self.status_code,
                        (self.response_body or "")[:1000],
                        # delivered_at = now (ISO-8601) if we got a response, else NULL.
                        # Must be a real value: a bound "datetime('now')" string would be
                        # stored verbatim as text, never evaluated by SQLite.
                        (
                            datetime.now(timezone.utc).isoformat()
                            if self.status_code is not None and self.status_code > 0
                            else None
                        ),
                    ),
                )
                return int(cur.lastrowid or 0)
            finally:
                conn.close()
        self._delivery_id = await asyncio.to_thread(_insert)
        return self

    async def __aexit__(self, *exc) -> None:
        return None


__all__ = ["send_webhook"]
