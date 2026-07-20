"""SSRF guard for repo cloning (Rebuild Phase 1, H3), exercised for real.

The clone flow's other tests monkeypatch `_validate_clone_target` away to reach
the git logic, so the guard itself had no coverage — the exact hole H3 is about.
These tests hit the real functions with a rejection matrix, using IP *literals*
so `getaddrinfo` resolves them offline with no DNS in the test path.
"""
from __future__ import annotations

import pytest

from mri.services.repo_cloner import (
    CloneError,
    _resolves_to_internal,
    _validate_clone_target,
    parse_repo_url,
)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",        # loopback
        "169.254.169.254",  # cloud metadata (link-local) — the classic SSRF target
        "10.0.0.1",         # private
        "192.168.1.1",      # private
        "172.16.0.1",       # private
        "0.0.0.0",          # unspecified
        "224.0.0.1",        # multicast
        "::1",              # loopback (v6)
    ],
)
def test_internal_addresses_are_refused(ip: str):
    assert _resolves_to_internal(ip) is True, f"{ip} must be treated as internal"


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1"])
def test_public_addresses_are_allowed(ip: str):
    assert _resolves_to_internal(ip) is False, f"{ip} is public and must not be refused"


def test_a_host_not_on_the_allowlist_is_refused():
    repo = parse_repo_url("https://evil.example.com/owner/name")
    with pytest.raises(CloneError, match="not permitted"):
        _validate_clone_target(repo, {})


def test_an_allowlisted_host_that_resolves_internal_is_still_refused():
    """Defense in depth: even a host the operator allow-listed is refused if it
    points at a private/loopback/metadata address (DNS-rebinding / typo'd host)."""
    repo = parse_repo_url("https://10.0.0.5/owner/name")
    config = {"clones": {"allowed_hosts": ["10.0.0.5"]}}
    with pytest.raises(CloneError, match="private, loopback, or link-local"):
        _validate_clone_target(repo, config)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://host/repo", "gopher://x/y"])
def test_non_git_schemes_are_rejected_at_parse(url: str):
    with pytest.raises(ValueError, match="scheme"):
        parse_repo_url(url)
