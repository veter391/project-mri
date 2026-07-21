"""End-to-end tests for the self-hosted dashboard.

Launches a real uvicorn server against an isolated DB, then drives the embedded
Next.js dashboard with a real browser. Also asserts the WCAG AA bar from
docs/QUALITY-BARS.md (zero serious/critical axe violations).

Run with: pytest tests/test_dashboard_e2e.py -v

Requires the dashboard to be built and embedded first:
    pnpm --filter @mri/dashboard build
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright")
from playwright.sync_api import (  # noqa: E402
    Page,
    expect,
    sync_playwright,  # noqa: E402
)

ADMIN_USER = "admin"
ADMIN_PASS = "test12345678"

# The dashboard is a build artifact (gitignored). Without it the server serves
# no /dashboard route at all, so skip loudly rather than fail obscurely.
_dashboard_index = Path(str(pkg_files("mri").joinpath("_frontend", "dashboard"))) / "index.html"
pytestmark = pytest.mark.skipif(
    not _dashboard_index.is_file(),
    reason="dashboard not built — run `pnpm --filter @mri/dashboard build`",
)


def _stop(proc: subprocess.Popen) -> None:
    """Terminate the server portably (Windows has no SIGINT for child procs)."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> str:
    """Launch uvicorn with an isolated DB and a known admin user."""
    tmp = tmp_path_factory.mktemp("dash-e2e")
    env = os.environ.copy()
    env["MRI_DB"] = str(tmp / "test.db")
    env["MRI_LOG_FORMAT"] = "text"
    env["MRI_LOG_LEVEL"] = "WARNING"

    init = subprocess.run(
        [sys.executable, "-m", "mri.cli", "init",
         "--username", ADMIN_USER, "--password", ADMIN_PASS, "--yes"],
        capture_output=True,
        env=env,
    )
    if init.returncode != 0:
        pytest.skip(f"mri init failed: {init.stderr.decode(errors='ignore')}")

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mri.api.app:app",
         "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"

    import httpx
    for _ in range(40):
        try:
            httpx.get(f"{base_url}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        _stop(proc)
        pytest.skip("server did not start")

    yield base_url

    _stop(proc)


@pytest.fixture(scope="function")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            yield browser.new_context().new_page()
        finally:
            browser.close()


def _login(page: Page, server: str, password: str = ADMIN_PASS) -> None:
    page.goto(f"{server}/dashboard/")
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible(timeout=15_000)
    page.get_by_label("Username").fill(ADMIN_USER)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


def _assert_no_serious_a11y_violations(page: Page) -> None:
    """WCAG AA bar: zero serious/critical axe violations (docs/QUALITY-BARS.md)."""
    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(page)
    blocking = [
        v for v in results.response.get("violations", [])
        if v.get("impact") in ("serious", "critical")
    ]
    assert not blocking, "axe violations: " + "; ".join(
        f"{v['id']} ({v['impact']}) x{len(v['nodes'])}" for v in blocking
    )


class TestDashboardE2E:
    def test_login_page_renders(self, server: str, page: Page):
        page.goto(f"{server}/dashboard/")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible(timeout=15_000)
        expect(page.get_by_label("Username")).to_be_visible()
        expect(page.get_by_label("Password")).to_be_visible()
        expect(page.get_by_role("button", name="Sign in")).to_be_enabled()

    def test_login_page_is_accessible(self, server: str, page: Page):
        page.goto(f"{server}/dashboard/")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible(timeout=15_000)
        _assert_no_serious_a11y_violations(page)

    def test_wrong_password_shows_error(self, server: str, page: Page):
        _login(page, server, password="definitely-wrong")
        expect(page.get_by_text("Invalid credentials.")).to_be_visible(timeout=15_000)
        # Must not have navigated into the authenticated view
        expect(page.get_by_role("button", name="sign out")).to_have_count(0)

    def test_login_shows_overview(self, server: str, page: Page):
        _login(page, server)
        expect(page.get_by_role("button", name="sign out")).to_be_visible(timeout=15_000)
        expect(page.get_by_text("Total scans")).to_be_visible()
        expect(page.get_by_text("recent scans")).to_be_visible()
        # Fresh DB — the empty state must be shown, not a fabricated number
        expect(page.get_by_text("No scans yet.")).to_be_visible()

    def test_overview_is_accessible(self, server: str, page: Page):
        _login(page, server)
        expect(page.get_by_role("button", name="sign out")).to_be_visible(timeout=15_000)
        _assert_no_serious_a11y_violations(page)

    def test_fusion_view_renders(self, server: str, page: Page):
        _login(page, server)
        expect(page.get_by_role("button", name="fusion")).to_be_visible(timeout=15_000)
        page.get_by_role("button", name="fusion").click()
        expect(
            page.get_by_role("heading", name="AI provenance & decisions")
        ).to_be_visible(timeout=15_000)
        expect(page.get_by_text("correlation, never causation", exact=False)).to_be_visible()
        # Fresh DB — honest empty state, not a fabricated project.
        expect(page.get_by_text("No projects yet.")).to_be_visible()

    def test_fusion_view_is_accessible(self, server: str, page: Page):
        _login(page, server)
        expect(page.get_by_role("button", name="fusion")).to_be_visible(timeout=15_000)
        page.get_by_role("button", name="fusion").click()
        expect(
            page.get_by_role("heading", name="AI provenance & decisions")
        ).to_be_visible(timeout=15_000)
        _assert_no_serious_a11y_violations(page)

    def test_sign_out_returns_to_login(self, server: str, page: Page):
        _login(page, server)
        expect(page.get_by_role("button", name="sign out")).to_be_visible(timeout=15_000)
        page.get_by_role("button", name="sign out").click()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible(timeout=15_000)
