"""Zero network egress (Rebuild Phase 5.4 / 11.3).

Local-first and privacy-by-default are the product's core promise. These tests
make it enforceable rather than aspirational: every outbound socket connection is
made to raise, then a full local scan and a session ingest are run. If any code
path reaches for the network, the connection attempt fails the test loudly.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import subprocess
from pathlib import Path

import pytest

from mri.db.migrator import migrate
from mri.db.repository import connect_sync, get_connection
from mri.ingest import ingest_workspace
from mri.services.scanner import Scanner, ScanOptions


def _is_loopback(address: object) -> bool:
    """True for a loopback / local destination. Loopback never leaves the host,
    and asyncio's own event-loop self-pipe uses it — egress means a *non*-loopback
    connection, so only those are the tripwire."""
    host = address[0] if isinstance(address, (tuple, list)) and address else address
    if not isinstance(host, str):  # AF_UNIX path, fd, etc. — never network egress
        return True
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a real hostname — treat as external, block it


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Any attempt to open a *non-loopback* connection raises — a tripwire for egress."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create = socket.create_connection

    def guarded_connect(self, address, *a, **k):  # noqa: ANN001
        if _is_loopback(address):
            return real_connect(self, address, *a, **k)
        raise AssertionError(f"outbound connection to {address!r} — MRI must stay local")

    def guarded_connect_ex(self, address, *a, **k):  # noqa: ANN001
        if _is_loopback(address):
            return real_connect_ex(self, address, *a, **k)
        raise AssertionError(f"outbound connection to {address!r} — MRI must stay local")

    def guarded_create(address, *a, **k):  # noqa: ANN001
        if _is_loopback(address):
            return real_create(address, *a, **k)
        raise AssertionError(f"outbound connection to {address!r} — MRI must stay local")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create)


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8", newline="\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    return path


def test_the_egress_tripwire_actually_fires(no_network):
    """No-op-guard guard: a real outbound connect must be blocked, so the tests
    below prove locality rather than passing vacuously."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(AssertionError, match="must stay local"):
            s.connect(("8.8.8.8", 443))
    finally:
        s.close()


def test_a_full_local_scan_makes_no_outbound_connection(no_network, tmp_path: Path):
    repo = _repo(tmp_path / "repo")
    report = asyncio.run(Scanner().scan(str(repo), opts=ScanOptions()))
    assert report.overall_health >= 0  # it ran to completion with the network sealed


def test_session_ingest_makes_no_outbound_connection(no_network, tmp_path: Path):
    db = tmp_path / "i.db"
    migrate(db)
    conn_s = connect_sync(db)
    try:
        pid = conn_s.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES ('/p', 'p', 'HEAD')"
        ).lastrowid
        conn_s.commit()
    finally:
        conn_s.close()

    workspace = tmp_path / "ws"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    async def go() -> None:
        async with get_connection(db) as conn:
            await ingest_workspace(conn, workspace, project_id=int(pid), home=home)

    asyncio.run(go())  # reading local logs must never touch the network
