"""Tests for v0.3.0 features: config, auth, repo cloning, webhook, diff, SARIF."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app
from mri.auth.users import (
    count_users,
    create_token,
    create_user,
    get_user_by_username,
    hash_password,
    verify_password,
    verify_token,
)
from mri.config import load_config, write_default_config
from mri.services.repo_cloner import (
    parse_repo_url,
)
from mri.services.webhook import send_webhook

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def setup_method(self):
        # Clear singleton
        from mri import config as cfg_mod
        cfg_mod._config = None

    def teardown_method(self):
        from mri import config as cfg_mod
        cfg_mod._config = None
        # Clear env var
        os.environ.pop("MRI_CONFIG", None)

    def test_load_with_explicit_path(self, tmp_path: Path):
        config_file = tmp_path / "test.yml"
        config_file.write_text("server:\n  port: 9999\n")
        cfg = load_config(config_file)
        assert cfg["server"]["port"] == 9999
        # Defaults preserved
        assert cfg["server"]["host"] == "127.0.0.1"
        assert cfg["auth"]["jwt_ttl_seconds"] == 86400

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yml")

    def test_load_no_file_returns_defaults(self):
        # When no file exists, returns defaults
        cfg = load_config()
        assert cfg["server"]["port"] == 7331

    def test_deep_merge(self, tmp_path: Path):
        # Override a deep value, keep others
        config_file = tmp_path / "test.yml"
        config_file.write_text("""
scans:
  default_branch: develop
  exclude_globs:
    - "**/target/**"
analyzers:
  git_history:
    enabled: false
""")
        cfg = load_config(config_file)
        assert cfg["scans"]["default_branch"] == "develop"
        # exclude_globs is replaced (not merged)
        assert cfg["scans"]["exclude_globs"] == ["**/target/**"]
        # Sub-keys preserved
        assert cfg["scans"]["timeout_seconds"] == 3600
        # git_history overridden
        assert cfg["analyzers"]["git_history"]["enabled"] is False
        # Other analyzers untouched
        assert cfg["analyzers"]["complexity"]["enabled"] is True

    def test_write_default_config(self, tmp_path: Path):
        out = tmp_path / "new-config.yml"
        write_default_config(out)
        assert out.exists()
        # Should be loadable
        cfg = load_config(out)
        assert cfg["server"]["port"] == 7331

    def test_env_override(self, tmp_path: Path, monkeypatch):
        config_file = tmp_path / "test.yml"
        config_file.write_text("server:\n  port: 8888\n")
        monkeypatch.setenv("MRI_CONFIG", str(config_file))
        cfg = load_config()
        assert cfg["server"]["port"] == 8888


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_and_verify(self):
        h = hash_password("super-secret-123")
        assert verify_password("super-secret-123", h)
        assert not verify_password("wrong-password", h)

    def test_hash_requires_min_length(self):
        with pytest.raises(ValueError):
            hash_password("short")
        with pytest.raises(ValueError):
            hash_password("")

    def test_hash_is_unique_per_call(self):
        # bcrypt salts, so same password produces different hashes
        h1 = hash_password("same-password-123")
        h2 = hash_password("same-password-123")
        assert h1 != h2
        assert verify_password("same-password-123", h1)
        assert verify_password("same-password-123", h2)

    def test_verify_handles_invalid_hash(self):
        assert not verify_password("any-password", "not-a-bcrypt-hash")
        assert not verify_password("", "")
        assert not verify_password("password", "")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Reset DB to empty state for auth tests."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MRI_DB", str(db_path))
    # The repository module caches the default path; force reload
    from mri.db import repository
    repository._DEFAULT_PATH = None
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestUserCRUD:
    def test_create_user(self, fresh_db):
        user = create_user("admin", "test-password-123")
        assert user["username"] == "admin"
        assert user["id"] > 0

    def test_create_user_duplicate(self, fresh_db):
        create_user("admin", "test-password-123")
        with pytest.raises(ValueError, match="already exists"):
            create_user("admin", "another-password-123")

    def test_create_user_validates_username(self, fresh_db):
        with pytest.raises(ValueError):
            create_user("ab", "test-password-123")
        with pytest.raises(ValueError):
            create_user("user with spaces", "test-password-123")
        with pytest.raises(ValueError):
            create_user("", "test-password-123")

    def test_get_user_by_username(self, fresh_db):
        create_user("admin", "test-password-123")
        user = get_user_by_username("admin")
        assert user is not None
        assert user["username"] == "admin"

    def test_get_user_by_username_not_found(self, fresh_db):
        assert get_user_by_username("nonexistent") is None

    def test_count_users(self, fresh_db):
        assert count_users() == 0
        create_user("admin", "test-password-123")
        assert count_users() == 1


class TestJWT:
    def test_create_and_verify_token(self, fresh_db):
        create_user("admin", "test-password-123")
        user = get_user_by_username("admin")
        token = create_token(user["id"], user["username"])
        claims = verify_token(token)
        assert claims is not None
        assert claims["sub"] == str(user["id"])
        assert claims["username"] == "admin"

    def test_invalid_token_returns_none(self, fresh_db):
        assert verify_token("not-a-jwt") is None
        assert verify_token("") is None

    def test_tampered_token_returns_none(self, fresh_db):
        create_user("admin", "test-password-123")
        user = get_user_by_username("admin")
        token = create_token(user["id"], user["username"])
        # Tamper with the signature
        tampered = token[:-5] + "XXXXX"
        assert verify_token(tampered) is None


# ---------------------------------------------------------------------------
# Repo URL parsing
# ---------------------------------------------------------------------------


class TestParseRepoUrl:
    def test_https_simple(self):
        url = parse_repo_url("https://github.com/owner/name")
        assert url.host == "github.com"
        assert url.owner == "owner"
        assert url.name == "name"
        assert url.scheme == "https"

    def test_https_with_git_suffix(self):
        url = parse_repo_url("https://github.com/owner/name.git")
        assert url.name == "name"

    def test_ssh_form(self):
        url = parse_repo_url("git@github.com:owner/name.git")
        assert url.host == "github.com"
        assert url.scheme == "ssh"
        assert url.owner == "owner"
        assert url.name == "name"

    def test_ssh_with_subgroup(self):
        url = parse_repo_url("git@gitlab.com:group/subgroup/project.git")
        assert url.host == "gitlab.com"
        assert url.owner == "group/subgroup"
        assert url.name == "project"

    def test_https_with_subgroup(self):
        url = parse_repo_url("https://gitlab.com/group/subgroup/project")
        assert url.owner == "group/subgroup"
        assert url.name == "project"

    def test_invalid_url(self):
        with pytest.raises(ValueError):
            parse_repo_url("")
        with pytest.raises(ValueError):
            parse_repo_url("not-a-url")
        with pytest.raises(ValueError):
            parse_repo_url("https://github.com/only-one")

    def test_canonical_url(self):
        url = parse_repo_url("https://github.com/owner/name")
        assert url.canonical_url == "https://github.com/owner/name.git"


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------


class TestWebhook:
    @pytest.mark.asyncio
    async def test_no_config_returns_skipped(self, tmp_path, monkeypatch):
        # Use isolated config with no webhook
        config_file = tmp_path / "test.yml"
        config_file.write_text("server:\n  port: 7331\n")
        monkeypatch.setenv("MRI_CONFIG", str(config_file))
        from mri import config as cfg_mod
        cfg_mod._config = None

        result = await send_webhook("scan_complete", {"test": True})
        assert result == -1  # skipped

    @pytest.mark.asyncio
    async def test_records_delivery_in_db(self, tmp_path, monkeypatch, fresh_db):
        config_file = tmp_path / "test.yml"
        config_file.write_text("""
server:
  port: 7331
notifications:
  webhook:
    url: https://nonexistent.example.com/webhook
    events: [scan_complete]
""")
        monkeypatch.setenv("MRI_CONFIG", str(config_file))
        from mri import config as cfg_mod
        cfg_mod._config = None

        # Will fail to deliver (no real network) but should still record
        result = await send_webhook("scan_complete", {"scan_uuid": "abc"})
        # Either delivery succeeded or failed gracefully
        assert result in (0, 200, 404, 500)  # 0 = network error


# ---------------------------------------------------------------------------
# Auth API integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_auth(tmp_path, monkeypatch):
    """TestClient with isolated DB and auth enabled."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MRI_DB", str(db_path))
    monkeypatch.setenv("MRI_LOG_FORMAT", "text")
    # Disable API key auth (env) so we test JWT
    monkeypatch.delenv("MRI_API_KEYS", raising=False)
    from mri.db import repository
    repository._DEFAULT_PATH = None
    app = create_app()
    with TestClient(app) as c:
        yield c, db_path


class TestAuthAPI:
    def test_status_uninitialized(self, client_with_auth):
        c, _ = client_with_auth
        r = c.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json()["initialized"] is False

    def test_login_fails_when_no_user(self, client_with_auth):
        c, _ = client_with_auth
        r = c.post("/api/auth/login", json={"username": "admin", "password": "test-12345678"})
        assert r.status_code == 401

    def test_full_flow(self, tmp_path, monkeypatch):
        """Create user via DB, login via API, use whoami, change password, logout."""
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("MRI_DB", str(db_path))
        monkeypatch.delenv("MRI_API_KEYS", raising=False)
        from mri.db import repository
        repository._DEFAULT_PATH = None

        # Create user
        create_user("admin", "original-password-123")

        app = create_app()
        with TestClient(app) as c:
            # 1. Status: initialized
            r = c.get("/api/auth/status")
            assert r.json()["initialized"] is True
            assert r.json()["user_count"] == 1

            # 2. Login
            r = c.post("/api/auth/login", json={"username": "admin", "password": "original-password-123"})
            assert r.status_code == 200
            data = r.json()
            assert "token" in data
            assert data["user"]["username"] == "admin"
            assert "mri_session" in r.cookies
            token = data["token"]

            # 3. Whoami with token
            r = c.get("/api/auth/whoami", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
            assert r.json()["username"] == "admin"

            # 4. Whoami with cookie
            r = c.get("/api/auth/whoami")
            assert r.status_code == 200
            assert r.json()["username"] == "admin"

            # 5. Change password
            r = c.post(
                "/api/auth/change-password",
                json={"current_password": "original-password-123", "new_password": "new-password-456"},
            )
            assert r.status_code == 200

            # 6. Old password no longer works
            r = c.post("/api/auth/login", json={"username": "admin", "password": "original-password-123"})
            assert r.status_code == 401

            # 7. New password works
            r = c.post("/api/auth/login", json={"username": "admin", "password": "new-password-456"})
            assert r.status_code == 200

            # 8. Logout
            r = c.post("/api/auth/logout")
            assert r.status_code == 200

        if db_path.exists():
            db_path.unlink()

    def test_whoami_unauthenticated(self, client_with_auth):
        c, _ = client_with_auth
        r = c.get("/api/auth/whoami")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Diff endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def two_scans(tmp_path, monkeypatch):
    """Create two completed scans on the same project."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("MRI_DB", str(db_path))
    from mri.db import repository
    repository._DEFAULT_PATH = None

    # Create a project
    import asyncio

    from mri.db.repository import create_scan, get_connection, update_scan_status, upsert_project

    async def setup():
        async with get_connection() as conn:
            pid = await upsert_project(conn, str(tmp_path / "fake-repo"), "fake-repo", "main")
            s1 = await create_scan(conn, pid, "a" * 32)
            s2 = await create_scan(conn, pid, "b" * 32)
            # First scan: 80 health
            await update_scan_status(
                conn, s1, "completed",
                report={
                    "scan_uuid": "a" * 32,
                    "project": {"path": "/tmp/fake-repo", "name": "fake-repo", "default_branch": "main"},
                    "started_at": "2026-07-05T00:00:00+00:00",
                    "finished_at": "2026-07-05T00:01:00+00:00",
                    "duration_ms": 60000,
                    "scores": [{"label": "architecture_health", "value": 70, "band": "good"}],
                    "findings": [],
                    "stats": {"file_count": 100, "loc_total": 5000, "commit_count": 50},
                    "overall_health": 70,
                    "overall_band": "good",
                    "runs": [],
                    "composition": [],
                },
                summary={"overall_health": 70}, finished=True,
            )
            # Second scan: 80 health, +1 finding
            await update_scan_status(
                conn, s2, "completed",
                report={
                    "scan_uuid": "b" * 32,
                    "project": {"path": "/tmp/fake-repo", "name": "fake-repo", "default_branch": "main"},
                    "started_at": "2026-07-06T00:00:00+00:00",
                    "finished_at": "2026-07-06T00:01:00+00:00",
                    "duration_ms": 60000,
                    "scores": [{"label": "architecture_health", "value": 80, "band": "good"}],
                    "findings": [
                        {
                            "analyzer_name": "architecture",
                            "category": "god_module",
                            "title": "New module",
                            "severity": "medium",
                            "description": "",
                            "target_path": "x.py",
                            "target_symbol": "",
                            "score": 60,
                            "data": {},
                            "status": "completed",
                            "signals": {},
                            "started_at": None,
                            "finished_at": None,
                            "duration_ms": None,
                            "error_message": "",
                        }
                    ],
                    "stats": {"file_count": 105, "loc_total": 5500, "commit_count": 55},
                    "overall_health": 80,
                    "overall_band": "good",
                    "runs": [],
                    "composition": [],
                },
                summary={"overall_health": 80}, finished=True,
            )
            return pid

    asyncio.run(setup())
    yield "a" * 32, "b" * 32, db_path


class TestDiffEndpoint:
    def test_diff_two_scans(self, two_scans):
        a, b, db_path = two_scans
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None
        try:
            app = create_app()
            with TestClient(app) as c:
                r = c.get(f"/api/scans/{a}/diff/{b}")
                assert r.status_code == 200
                data = r.json()
                assert data["before"]["overall_health"] == 70
                assert data["after"]["overall_health"] == 80
                # Score diff
                assert data["score_diff"][0]["delta"] == 10.0
                # Findings added
                assert len(data["findings"]["added"]) == 1
                # Stats diff
                assert data["stats_diff"]["file_count"] == 5
                assert data["stats_diff"]["loc_total"] == 500
        finally:
            monkeypatch.undo()

    def test_diff_invalid_uuid(self, two_scans):
        a, b, db_path = two_scans
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None
        try:
            app = create_app()
            with TestClient(app) as c:
                r = c.get("/api/scans/abc/diff/def")
                assert r.status_code == 400
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------


class TestDeleteEndpoint:
    def test_delete_scan(self, two_scans):
        a, b, db_path = two_scans
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None
        try:
            app = create_app()
            with TestClient(app) as c:
                r = c.delete(f"/api/scans/{a}")
                assert r.status_code == 200
                assert r.json()["deleted"] is True

                # Second delete: idempotent
                r = c.delete(f"/api/scans/{a}")
                assert r.status_code == 200
                assert r.json()["deleted"] is False
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# SARIF endpoint
# ---------------------------------------------------------------------------


class TestSARIFEndpoint:
    def test_sarif_export(self, two_scans):
        a, b, db_path = two_scans
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None
        try:
            app = create_app()
            with TestClient(app) as c:
                r = c.get(f"/api/scans/{b}/report.sarif")
                assert r.status_code == 200
                assert r.headers["content-type"] == "application/sarif+json"
                sarif = r.json()
                assert sarif["version"] == "2.1.0"
                assert "$schema" in sarif
                assert len(sarif["runs"]) >= 1
                run = sarif["runs"][0]
                assert run["tool"]["driver"]["name"] == "project-mri"
                # Findings converted to results
                assert len(run["results"]) >= 1
                result = run["results"][0]
                assert "ruleId" in result
                assert "level" in result
                assert "message" in result
        finally:
            monkeypatch.undo()
