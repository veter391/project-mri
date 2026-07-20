"""The fail-closed bind posture (H2 / ADR-013).

Loopback is trusted and needs no auth; a non-loopback bind is refused unless auth
is configured or the operator explicitly opts out. These pin that a server can
never be *accidentally* exposed unauthenticated.
"""
from __future__ import annotations

import pytest

from mri import security
from mri.security import ALLOW_INSECURE_ENV, assert_safe_bind


@pytest.fixture(autouse=True)
def _no_ambient_auth(monkeypatch: pytest.MonkeyPatch):
    """Default every test to 'no auth configured, no override' so the posture is
    exercised deterministically regardless of the developer's real environment."""
    monkeypatch.setattr(security, "is_auth_enabled", lambda: False)
    monkeypatch.delenv(ALLOW_INSECURE_ENV, raising=False)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", ""])
def test_loopback_needs_no_auth(host: str):
    assert_safe_bind(host)  # must not raise


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "10.0.0.5"])
def test_nonloopback_without_auth_is_refused(host: str):
    with pytest.raises(RuntimeError, match="Refusing to bind"):
        assert_safe_bind(host)


def test_nonloopback_with_user_auth_is_allowed():
    assert_safe_bind("0.0.0.0", has_user_auth=True)  # dashboard user gates the API


def test_nonloopback_with_configured_auth_is_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(security, "is_auth_enabled", lambda: True)
    assert_safe_bind("0.0.0.0")  # API key / user configured


def test_explicit_insecure_override_is_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(ALLOW_INSECURE_ENV, "1")
    assert_safe_bind("0.0.0.0")  # operator knowingly accepts an unauth'd public bind
