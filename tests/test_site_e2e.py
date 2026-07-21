"""The public marketing site (apps/web), driven in a real browser.

Mirrors the dashboard e2e bar: every route loads, has no console/request errors,
and passes axe with zero serious/critical violations. Skips loudly if the site
is not built (its Next output is gitignored) or Playwright is unavailable, so a
bare checkout does not fail obscurely.

Run with: pytest tests/test_site_e2e.py -v
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "apps" / "web"
_BUILT = (WEB / ".next" / "BUILD_ID").is_file()

pytestmark = pytest.mark.skipif(
    not _BUILT,
    reason="site not built — run `NODE_ENV=production pnpm --filter web build`",
)

playwright = pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

ROUTES = [
    "/", "/features", "/architecture", "/install", "/manifesto", "/roadmap",
    "/about", "/comparison", "/self-host", "/demo", "/docs",
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url() -> str:
    port = _free_port()
    env = {**os.environ, "NODE_ENV": "production"}
    proc = subprocess.Popen(
        ["pnpm", "exec", "next", "start", "-p", str(port)],
        cwd=str(WEB), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        shell=(os.name == "nt"),
    )
    url = f"http://127.0.0.1:{port}"
    try:
        import httpx

        for _ in range(60):
            try:
                httpx.get(url + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            proc.terminate()
            pytest.skip("site server did not start")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            yield browser.new_context().new_page()
        finally:
            browser.close()


@pytest.mark.parametrize("route", ROUTES)
def test_route_loads_cleanly(base_url: str, page: Page, route: str):
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("requestfailed", lambda r: errors.append(f"requestfailed {r.url}"))
    resp = page.goto(base_url + route, wait_until="networkidle", timeout=20_000)
    assert resp is not None and resp.status < 400, f"{route} -> HTTP {resp.status if resp else 'no response'}"
    assert not errors, f"{route} console/request errors: {errors[:3]}"


def test_pages_are_accessible(base_url: str, page: Page):
    """WCAG AA bar: zero serious/critical axe violations on every route."""
    from axe_playwright_python.sync_playwright import Axe

    offenders: dict[str, list[str]] = {}
    for route in ROUTES:
        page.goto(base_url + route, wait_until="networkidle", timeout=20_000)
        results = Axe().run(page)
        blocking = [
            f"{v['id']}({v['impact']})x{len(v['nodes'])}"
            for v in results.response.get("violations", [])
            if v.get("impact") in ("serious", "critical")
        ]
        if blocking:
            offenders[route] = blocking
    assert not offenders, f"axe violations: {offenders}"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
