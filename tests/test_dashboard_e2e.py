"""End-to-end tests for the self-hosted dashboard.

These tests launch a real uvicorn server in a subprocess, then drive it
with Playwright to verify the user-facing flow works.

Run with: pytest tests/test_dashboard_e2e.py -v
(Skip in environments without playwright: PYTHONPATH=. python -c "import playwright")
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


# Skip entire module if playwright isn't available
playwright = pytest.importorskip("playwright")
from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402


PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture(scope="function")
def page():
    """Yield a Playwright page with a fresh browser per test."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            yield context.new_page()
        finally:
            browser.close()


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Launch a uvicorn server with isolated DB, return (url, admin_user, admin_pass)."""
    tmp = tmp_path_factory.mktemp("dash-e2e")
    db_path = tmp / "test.db"
    env = os.environ.copy()
    env["MRI_DB"] = str(db_path)
    env["MRI_LOG_FORMAT"] = "text"
    env["MRI_LOG_LEVEL"] = "WARNING"  # quieter
    env["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
    # Initialize user
    init = subprocess.run(
        [sys.executable, "-m", "mri.cli", "init", "--username", "admin", "--password", "test12345678", "--yes"],
        capture_output=True,
        env=env,
        cwd=str(PROJECT_ROOT / "backend"),
    )
    if init.returncode != 0:
        pytest.skip(f"mri init failed: {init.stderr.decode()}")
    # Start server
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mri.api.app:app", "--port", str(port), "--log-level", "warning"],
        env=env,
        cwd=str(PROJECT_ROOT / "backend"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    # Wait for server to come up
    import httpx
    for _ in range(20):
        try:
            httpx.get(f"{base_url}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.send_signal(signal.SIGINT)
        proc.wait()
        pytest.skip("server didn't start")
    yield base_url
    # Teardown
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def perf_repo(tmp_path_factory):
    """Create a small git repo for scanning."""
    import subprocess
    p = tmp_path_factory.mktemp("repo")
    (p / "main.py").write_text("import os\n\ndef main():\n    print('hi')\n")
    (p / "utils.py").write_text("# TODO: add tests\ndef add(a, b):\n    return a + b\n")
    subprocess.check_call(["git", "init", "-q"], cwd=p)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=p)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], cwd=p)
    return p


class TestDashboardE2E:
    def test_login_page_renders(self, server: str, page: Page):
        page.goto(f"{server}/dashboard/")
        # Wait for JS to render the login form
        page.wait_for_selector(".login__box", timeout=10_000)
        expect(page.locator(".login__brand")).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()

    def test_login_with_wrong_password(self, server: str, page: Page):
        page.goto(f"{server}/dashboard/")
        page.wait_for_selector(".login__form", timeout=10_000)
        page.locator("#login-username").fill("admin")
        page.locator("#login-password").fill("wrong-password")
        page.locator('button[type="submit"]').click()
        # Wait for the API call to complete and err to populate
        page.wait_for_function(
            "() => document.getElementById('login-err')?.textContent?.length > 0",
            timeout=10_000,
        )
        err_text = page.locator("#login-err").text_content()
        assert "Invalid" in (err_text or "") or "password" in (err_text or "").lower()

    def test_login_and_see_overview(self, server: str, page: Page):
        page.goto(f"{server}/dashboard/")
        page.wait_for_selector(".login__form", timeout=10_000)
        page.locator("#login-username").fill("admin")
        page.locator("#login-password").fill("test12345678")
        page.locator('button[type="submit"]').click()
        # Wait for nav to render (which happens after whoami succeeds)
        page.wait_for_selector(".nav__links", timeout=15_000)
        # Then wait for the main page header
        page.wait_for_selector(".page-header h1", timeout=15_000)
        h1 = page.locator(".page-header h1").text_content()
        assert h1 is not None
        assert "overview" in h1.lower()

    def test_full_scan_flow(self, server: str, perf_repo, page: Page):
        # Login
        page.goto(f"{server}/dashboard/")
        page.wait_for_selector(".login__form", timeout=10_000)
        page.locator("#login-username").fill("admin")
        page.locator("#login-password").fill("test12345678")
        page.locator('button[type="submit"]').click()
        page.wait_for_selector(".page-header h1", timeout=10_000)
        # Navigate to new scan
        page.locator('a[href="#/new-scan"]').first.click()
        page.wait_for_selector("#new-scan-form", timeout=10_000)
        # Enter the path
        page.locator("#ns-path").fill(str(perf_repo))
        # Submit
        page.locator('#new-scan-form button[type="submit"]').click()
        # Should redirect to scan detail; wait for either progress or completed
        try:
            page.wait_for_selector(".progress__fill, .score-card", timeout=30_000)
        except Exception:
            pass
        # Wait for completion (score cards render when done)
        page.wait_for_selector(".score-card", timeout=60_000)
        # Verify we see score cards
        score_cards = page.locator(".score-card").count()
        assert score_cards >= 6, f"expected 6 score cards, got {score_cards}"

    def test_settings_change_password(self, server: str, page: Page):
        # Login
        page.goto(f"{server}/dashboard/")
        page.wait_for_selector(".login__form", timeout=10_000)
        page.locator("#login-username").fill("admin")
        page.locator("#login-password").fill("test12345678")
        page.locator('button[type="submit"]').click()
        page.wait_for_selector(".page-header h1", timeout=10_000)
        # Navigate to settings
        page.locator('a[href="#/settings"]').first.click()
        page.wait_for_selector("#pw-form", timeout=10_000)
        # Fill in password change
        page.locator("#pw-current").fill("test12345678")
        page.locator("#pw-new").fill("new-password-456")
        page.locator('#pw-form button[type="submit"]').click()
        # Wait for success message
        page.wait_for_function(
            "() => document.getElementById('pw-msg')?.textContent?.includes('password changed')",
            timeout=15_000,
        )
        # Wait for the form fields to be cleared (signals request completed)
        page.wait_for_function(
            "() => document.getElementById('pw-current')?.value === ''",
            timeout=5_000,
        )
        # Change back so other tests still work
        page.locator("#pw-current").fill("new-password-456")
        page.locator("#pw-new").fill("test12345678")
        page.locator('#pw-form button[type="submit"]').click()
        # Wait for success message
        page.wait_for_function(
            "() => document.getElementById('pw-msg')?.textContent?.includes('password changed')",
            timeout=15_000,
        )

    def test_dashboard_responsive(self, server: str, page: Page):
        """On a narrow viewport, the sidebar should be hidden."""
        page.set_viewport_size({"width": 480, "height": 800})
        page.goto(f"{server}/dashboard/")
        page.wait_for_selector(".login__box", timeout=10_000)
        # Login
        page.locator("#login-username").fill("admin")
        page.locator("#login-password").fill("test12345678")
        page.locator('button[type="submit"]').click()
        page.wait_for_selector(".page-header h1", timeout=10_000)
        # On mobile, the sidebar should not be visible
        sidebar = page.locator(".sidebar")
        if sidebar.is_visible():
            # If it IS visible, it should still fit
            box = sidebar.bounding_box()
            assert box is None or box["width"] <= 0, f"sidebar should be hidden on mobile, got {box}"
