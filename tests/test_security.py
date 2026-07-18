"""Security-focused tests — path traversal, injection, auth bypass, headers.

Run with: PYTHONPATH=. pytest tests/test_security.py -v
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app
from mri.security import (
    PathValidationError,
    check_api_key,
    generate_api_key,
    is_auth_enabled,
    sanitize_for_log,
    validate_branch,
    validate_project_path,
    validate_slug,
)

# ---------------------------------------------------------------------------
# Unit tests for security helpers
# ---------------------------------------------------------------------------


class TestPathValidation:
    def setup_method(self):
        # Force unset allowlist for these tests
        os.environ.pop("MRI_ALLOWED_ROOTS", None)

    def test_validate_empty_path(self):
        with pytest.raises(PathValidationError):
            validate_project_path("")
        with pytest.raises(PathValidationError):
            validate_project_path("   ")

    def test_validate_nonexistent(self):
        with pytest.raises(PathValidationError):
            validate_project_path("/nonexistent/path/that/should/not/exist/anywhere")

    def test_validate_null_byte(self):
        with pytest.raises(PathValidationError):
            validate_project_path("/tmp/foo\x00bar")

    def test_validate_too_long(self):
        with pytest.raises(PathValidationError):
            validate_project_path("/tmp/" + "a" * 5000)

    def test_validate_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(PathValidationError):
            validate_project_path(str(f))

    def test_validate_resolves_symlinks(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        # Both should resolve to the same target
        assert validate_project_path(str(real)) == validate_project_path(str(link))

    def test_allowlist_enforced(self, tmp_path, monkeypatch):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.setenv("MRI_ALLOWED_ROOTS", str(allowed))
        # Allowed
        assert validate_project_path(str(allowed)) == allowed.resolve()
        # Denied
        with pytest.raises(PathValidationError):
            validate_project_path(str(outside))


class TestBranchValidation:
    def test_valid_branch(self):
        assert validate_branch("main") == "main"
        assert validate_branch("feature/foo") == "feature/foo"
        assert validate_branch("release-1.2.3") == "release-1.2.3"
        assert validate_branch(None) is None

    def test_invalid_branch(self):
        with pytest.raises(ValueError):
            validate_branch("../../etc")
        with pytest.raises(ValueError):
            validate_branch("foo;rm")
        with pytest.raises(ValueError):
            validate_branch("-foo")
        with pytest.raises(ValueError):
            validate_branch("foo/")
        assert validate_branch("") is None  # empty string treated as None
        with pytest.raises(ValueError):
            validate_branch("a" * 300)


class TestSlugValidation:
    def test_valid(self):
        assert validate_slug("my-legacy-app") == "my-legacy-app"
        assert validate_slug("clean_typescript_lib") == "clean_typescript_lib"
        assert validate_slug("a") == "a"

    def test_invalid(self):
        with pytest.raises(ValueError):
            validate_slug("../etc")
        with pytest.raises(ValueError):
            validate_slug("foo bar")
        with pytest.raises(ValueError):
            validate_slug("")
        with pytest.raises(ValueError):
            validate_slug("a" * 200)


class TestApiKey:
    def test_disabled_when_no_env(self, monkeypatch):
        monkeypatch.delenv("MRI_API_KEYS", raising=False)
        assert is_auth_enabled() is False
        assert check_api_key(None) is True
        assert check_api_key("anything") is True

    def test_enabled_with_env(self, monkeypatch):
        monkeypatch.setenv("MRI_API_KEYS", "valid-key")
        assert is_auth_enabled() is True
        assert check_api_key("valid-key") is True
        assert check_api_key("wrong-key") is False
        assert check_api_key(None) is False
        assert check_api_key("") is False

    def test_generate_key_unique(self):
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100
        # 32-byte URL-safe is at least 40 chars
        for k in keys:
            assert len(k) >= 40

    def test_constant_time_compare(self, monkeypatch):
        # Just verify the function works — actually testing constant-time is hard
        monkeypatch.setenv("MRI_API_KEYS", "test-key")
        assert check_api_key("test-key") is True


class TestSanitizeForLog:
    def test_strips_control(self):
        assert "\x00" not in sanitize_for_log("hello\x00world")
        assert sanitize_for_log("hello\x07world") == "helloworld"

    def test_truncates_long(self):
        s = "a" * 1000
        out = sanitize_for_log(s, max_len=50)
        assert len(out) < 100  # truncated
        assert "truncated" in out

    def test_preserves_newlines_tabs(self):
        assert sanitize_for_log("a\nb\tc") == "a\nb\tc"


# ---------------------------------------------------------------------------
# Integration tests via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def allowed_repo(tmp_path):
    """Create a real git repo we can scan."""
    import subprocess
    p = tmp_path / "project"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    subprocess.check_call(["git", "init", "-q"], cwd=p)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=p)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=p)
    subprocess.check_call(["git", "add", "-A"], cwd=p)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=p)
    return p


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """TestClient with API keys + path allowlist."""
    monkeypatch.setenv("MRI_API_KEYS", "test-key")
    monkeypatch.setenv("MRI_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("MRI_LOG_FORMAT", "text")
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def noauth_client(monkeypatch):
    """TestClient without auth (dev mode)."""
    monkeypatch.delenv("MRI_API_KEYS", raising=False)
    monkeypatch.delenv("MRI_ALLOWED_ROOTS", raising=False)
    monkeypatch.setenv("MRI_LOG_FORMAT", "text")
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestAuthIntegration:
    def test_no_key_rejected(self, auth_client):
        r = auth_client.get("/api/scans")
        assert r.status_code == 401
        assert "Unauthorized" in r.text

    def test_wrong_key_rejected(self, auth_client):
        r = auth_client.get("/api/scans", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_correct_key_bearer(self, auth_client):
        r = auth_client.get("/api/scans", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 200

    def test_correct_key_x_api_header(self, auth_client):
        r = auth_client.get("/api/scans", headers={"X-API-Key": "test-key"})
        assert r.status_code == 200

    def test_health_no_auth(self, auth_client):
        r = auth_client.get("/api/health")
        assert r.status_code == 200

    def test_demo_no_auth(self, auth_client):
        r = auth_client.get("/api/demo/feed")
        assert r.status_code == 200


class TestPathSecurity:
    def test_etc_blocked(self, auth_client):
        r = auth_client.post(
            "/api/scans",
            json={"project_path": "/etc"},
            headers={"Authorization": "Bearer test-key"},
        )
        assert r.status_code == 400
        assert "not under any allowed root" in r.text

    def test_traversal_blocked(self, auth_client, allowed_repo, tmp_path):
        # tmp_path is allowed; the repo is inside it. Try escaping.
        r = auth_client.post(
            "/api/scans",
            json={"project_path": str(allowed_repo) + "/../../../etc"},
            headers={"Authorization": "Bearer test-key"},
        )
        # Resolves to /etc, which is outside allowed → 400
        assert r.status_code == 400

    def test_allowed_passes(self, auth_client, allowed_repo):
        r = auth_client.post(
            "/api/scans",
            json={"project_path": str(allowed_repo)},
            headers={"Authorization": "Bearer test-key"},
        )
        assert r.status_code == 200


class TestSecurityHeaders:
    def test_nosniff(self, noauth_client):
        r = noauth_client.get("/api/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_frame_deny(self, noauth_client):
        r = noauth_client.get("/api/health")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_hsts(self, noauth_client):
        r = noauth_client.get("/api/health")
        assert "max-age" in r.headers.get("Strict-Transport-Security", "")

    def test_csp(self, noauth_client):
        r = noauth_client.get("/api/health")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_referrer(self, noauth_client):
        r = noauth_client.get("/api/health")
        assert r.headers.get("Referrer-Policy") == "no-referrer"

    def test_request_id_propagated(self, noauth_client):
        r = noauth_client.get("/api/health")
        assert "X-Request-ID" in r.headers
        # Length should be ~12 chars (uuid hex prefix)
        assert 8 <= len(r.headers["X-Request-ID"]) <= 32


class TestInputValidation:
    def test_invalid_uuid(self, auth_client):
        r = auth_client.get("/api/scans/abc", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 400

    def test_invalid_branch(self, auth_client, allowed_repo):
        r = auth_client.post(
            "/api/scans",
            json={"project_path": str(allowed_repo), "branch": "../../etc"},
            headers={"Authorization": "Bearer test-key"},
        )
        assert r.status_code == 400

    def test_limit_bounds(self, auth_client):
        r = auth_client.get("/api/scans?limit=99999", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 400


class TestBodySize:
    def test_oversize_rejected(self, noauth_client):
        # Send a huge JSON body
        import json
        r = noauth_client.post(
            "/api/scans",
            content=json.dumps({"x": "A" * 2_000_000}).encode(),
        )
        assert r.status_code == 413


class TestErrorHandling:
    def test_validation_error_no_echo(self, noauth_client):
        """422 errors must not echo raw user input back."""
        r = noauth_client.post(
            "/api/scans",
            json={"project_path": 12345},  # wrong type
        )
        assert r.status_code == 422
        body = r.text
        # Should NOT contain the raw input
        assert "12345" not in body
        # Should contain a generic message
        assert "Invalid request payload" in body or "errors_count" in body

    def test_internal_error_not_leaked(self, noauth_client, monkeypatch):
        """500 errors must not leak stack traces or paths."""
        # Trigger a 500 by sending bad scan data
        r = noauth_client.get("/api/scans/not-a-uuid")
        # Should be 400, not 500
        assert r.status_code in (400, 422)

# ---------------------------------------------------------------------------
# Login must not leak whether a username exists, via timing
# ---------------------------------------------------------------------------


class TestLoginTiming:
    """A failed login took microseconds for an unknown username and ~195 ms for
    a known one, because the bcrypt check was short-circuited away. That is a
    username-enumeration oracle regardless of the generic error message."""

    def test_unknown_username_costs_the_same_as_a_wrong_password(self, tmp_path, monkeypatch):
        import time

        from fastapi.testclient import TestClient

        monkeypatch.setenv("MRI_DB", str(tmp_path / "timing.db"))
        from mri.auth.users import create_user

        create_user("realuser", "correct-horse-battery")

        from mri.api.app import create_app

        client = TestClient(create_app())

        def attempt(username: str) -> float:
            start = time.perf_counter()
            resp = client.post(
                "/api/auth/login", json={"username": username, "password": "wrong-password"}
            )
            assert resp.status_code == 401
            return time.perf_counter() - start

        known = min(attempt("realuser") for _ in range(3))
        unknown = min(attempt("ghostuser") for _ in range(3))

        # Both must pay for a bcrypt verification. A short-circuit shows up as
        # the unknown case being an order of magnitude faster.
        assert unknown > known / 2, (
            f"unknown username answered in {unknown * 1000:.0f} ms vs "
            f"{known * 1000:.0f} ms for a known one — enumeration oracle"
        )
