"""`mri` CLI — subcommands: init, scan, serve, watch, demo, backup, restore, upgrade, reset, ui."""
from __future__ import annotations

import asyncio
import getpass
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import uvicorn

from mri.services.demo_feed import generate_demo_report
from mri.services.report_generator import render_html, render_json, write_report_files
from mri.services.scanner import Scanner, ScanOptions


@click.group()
@click.version_option(package_name="project-mri")
def cli() -> None:
    """project-mri — codebase MRI scanner."""
    pass


# ---------------------------------------------------------------------------
# mri init — first-time setup
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--username", default=None, help="Admin username (default: current OS user)")
@click.option("--password", default=None, help="Admin password (default: prompt)")
@click.option(
    "--config-path",
    default=None,
    type=click.Path(),
    help="Where to write the config file (default: ~/.config/project-mri/config.yml)",
)
@click.option("--yes", "-y", is_flag=True, help="Non-interactive (use defaults)")
def init(username: str | None, password: str | None, config_path: str | None, yes: bool) -> None:
    """Initialize a fresh installation: create admin user, write config, prep DB."""
    click.echo("→ Initializing project-mri", err=True)

    # 1. Username
    if not username:
        username = getpass.getuser() or "admin"
    if not yes:
        new_username = click.prompt("  Admin username", default=username)
        if new_username:
            username = new_username

    # 2. Password
    if not password:
        if yes:
            click.echo("✗ --password required in non-interactive mode", err=True)
            sys.exit(2)
        while True:
            pwd1 = click.prompt("  Admin password", hide_input=True, confirmation_prompt=False)
            if len(pwd1) < 8:
                click.echo("  ! password must be at least 8 characters", err=True)
                continue
            pwd2 = click.prompt("  Confirm password", hide_input=True, confirmation_prompt=False)
            if pwd1 != pwd2:
                click.echo("  ! passwords do not match", err=True)
                continue
            password = pwd1
            break

    # 3. Create the user
    from mri.auth.users import count_users, create_user
    if count_users() > 0:
        if not click.confirm("  An admin user already exists. Create another?", default=False):
            click.echo("✓ keeping existing user", err=True)
        else:
            try:
                create_user(username, password)
                click.echo(f"  ✓ user '{username}' created", err=True)
            except ValueError as e:
                click.echo(f"✗ {e}", err=True)
                sys.exit(1)
    else:
        try:
            create_user(username, password)
            click.echo(f"  ✓ user '{username}' created", err=True)
        except ValueError as e:
            click.echo(f"✗ {e}", err=True)
            sys.exit(1)

    # 4. Write default config
    if config_path:
        cfg_path = Path(config_path).expanduser()
    else:
        cfg_path = Path.home() / ".config" / "project-mri" / "config.yml"
    if not cfg_path.exists():
        from mri.config import write_default_config
        write_default_config(cfg_path)
        click.echo(f"  ✓ config written → {cfg_path}", err=True)
    else:
        click.echo(f"  → config already exists at {cfg_path}", err=True)

    # 5. Print next steps
    from mri.config import get_config
    from mri.db.repository import default_db_path
    cfg = get_config()
    port = cfg.get("server", {}).get("port", 7331)
    click.echo("", err=True)
    click.echo("✓ Initialization complete!", err=True)
    click.echo("", err=True)
    click.echo("Next steps:", err=True)
    click.echo("  • Start the server:  mri serve", err=True)
    click.echo(f"  • Open dashboard:     http://localhost:{port}/dashboard/", err=True)
    click.echo("  • Run a scan:         mri scan /path/to/your/repo", err=True)
    click.echo(f"  • Database:           {default_db_path()}", err=True)


# ---------------------------------------------------------------------------
# mri scan — one-shot scan
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("project_path")
@click.option("--branch", default=None, help="Git branch to analyze")
@click.option("--output", "-o", default="./mri-report.html", help="Output path (HTML)")
@click.option("--json-out", default=None, help="Also write JSON to this path")
@click.option("--depth", type=int, default=None, help="Shallow clone depth (URL only)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
def scan(project_path: str, branch: str | None, output: str, json_out: str | None, depth: int | None, quiet: bool) -> None:
    """Scan a project (local path or git URL) and produce an HTML report."""
    click.echo(f"→ scanning {project_path}", err=True)

    async def go() -> None:
        async def on_progress(progress) -> None:
            if not quiet:
                bar_width = 30
                filled = int(progress.percent / 100 * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                click.echo(f"\r  [{bar}] {progress.percent:5.1f}% · {progress.phase:8s} · {progress.detail}", nl=False, err=True)

        scanner = Scanner(on_progress=on_progress if not quiet else None)
        report = await scanner.scan(
            project_path,
            opts=ScanOptions(branch=branch, depth=depth),
        )
        if not quiet:
            click.echo("", err=True)

        out = Path(output).resolve()
        files = write_report_files(report, out.parent)
        # Rename to user-specified path
        if str(out) != str(files["html"]):
            files["html"].rename(out)
        if json_out:
            Path(json_out).write_text(render_json(report), encoding="utf-8")
        click.echo(f"✓ report saved → {out}", err=True)
        click.echo(f"  overall health: {report.overall_health:.1f}/100 ({report.overall_band})", err=True)
        click.echo(f"  duration: {report.duration_ms} ms", err=True)
        click.echo(f"  findings: {len(report.findings)}", err=True)

    asyncio.run(go())


# ---------------------------------------------------------------------------
# mri watch — re-scan on file change
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--branch", default=None, help="Git branch to analyze")
@click.option("--output-dir", default="./mri-reports/", help="Where to write reports")
@click.option("--depth", type=int, default=None, help="Shallow clone depth (URL only)")
@click.option("--debounce", type=float, default=2.0, help="Seconds to wait before re-scanning")
@click.option("--quiet", "-q", is_flag=True, help="Suppress per-scan output")
def watch(project_path: str, branch: str | None, output_dir: str, depth: int | None, debounce: float, quiet: bool) -> None:
    """Watch a directory and re-scan whenever files change."""
    click.echo(f"→ watching {project_path} (Ctrl+C to stop)", err=True)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    from mri.services.watcher import RepoWatcher

    def rescan() -> None:
        async def _go() -> None:
            try:
                scanner = Scanner()
                report = await scanner.scan(
                    project_path,
                    opts=ScanOptions(branch=branch, depth=depth),
                )
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                html = output_path / f"scan-{ts}.html"
                json_path = output_path / f"scan-{ts}.json"
                html.write_text(render_html(report), encoding="utf-8")
                json_path.write_text(render_json(report), encoding="utf-8")
                if not quiet:
                    click.echo(
                        f"  ✓ rescanned at {ts} → {html}  (health: {report.overall_health:.1f})",
                        err=True,
                    )
            except Exception as e:  # nosem: bandit
                click.echo(f"  ✗ rescan failed: {e}", err=True)

        asyncio.run(_go())

    watcher = RepoWatcher(project_path, on_change=rescan, debounce_seconds=debounce)
    try:
        watcher.start()
        # Block forever (or until Ctrl+C)
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        click.echo("", err=True)
        click.echo("→ stopping watcher", err=True)
    finally:
        watcher.stop()


# ---------------------------------------------------------------------------
# mri serve — run the API server
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--host", default=None, help="Bind host (default: from .mri.yml or 127.0.0.1)")
@click.option("--port", default=None, type=int, help="Bind port (default: from .mri.yml or 7331)")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes")
def serve(host: str | None, port: int | None, reload: bool) -> None:
    """Run the HTTP API server + dashboard."""
    from mri.config import get_config
    cfg = get_config()
    if host is None:
        host = cfg.get("server", {}).get("host", "127.0.0.1")
    if port is None:
        port = cfg.get("server", {}).get("port", 7331)
    click.echo(f"→ starting project-mri at http://{host}:{port}", err=True)
    click.echo(f"  API:        http://{host}:{port}/api/docs", err=True)
    click.echo(f"  Dashboard:  http://{host}:{port}/dashboard/", err=True)
    uvicorn.run("mri.api.app:app", host=host, port=port, reload=reload, log_level="info")


# ---------------------------------------------------------------------------
# mri demo — synthetic report
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--slug", default="my-legacy-app", help="Demo project slug")
@click.option("--output", "-o", default="./mri-demo-report.html", help="Output path (HTML)")
def demo(slug: str, output: str) -> None:
    """Generate a demo report without scanning a real project."""
    click.echo(f"→ generating demo report for '{slug}'", err=True)
    report = generate_demo_report(slug)
    report.scan_uuid = "demo-" + slug
    out = Path(output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(report), encoding="utf-8")
    click.echo(f"✓ demo report saved → {out}", err=True)
    click.echo(f"  overall health: {report.overall_health:.1f}/100 ({report.overall_band})", err=True)


# ---------------------------------------------------------------------------
# mri backup / restore
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("output", type=click.Path())
@click.option("--include-clones", is_flag=True, help="Also include cached clones")
def backup(output: str, include_clones: bool) -> None:
    """Back up the database to a single file."""
    import tarfile

    from mri.db.repository import default_db_path

    db_path = default_db_path()
    if not db_path.exists():
        click.echo("✗ no database to back up", err=True)
        sys.exit(1)
    cfg_path = Path.home() / ".config" / "project-mri" / "config.yml"
    cache_dir = cfg_path.parent / "repos"

    out = Path(output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    click.echo(f"→ backing up to {out}", err=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(str(db_path), arcname=f"db/{db_path.name}")
        if cfg_path.exists():
            tar.add(str(cfg_path), arcname=f"config/{cfg_path.name}")
        if include_clones and cache_dir.exists():
            tar.add(str(cache_dir), arcname="repos")
    click.echo(f"✓ backup complete ({out.stat().st_size:,} bytes)", err=True)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def restore(input_file: str, yes: bool) -> None:
    """Restore the database from a backup file."""
    import tarfile

    from mri.db.repository import default_db_path

    if not yes:
        click.confirm(
            f"  This will replace your current database at {default_db_path()}. Continue?",
            abort=True,
        )

    src = Path(input_file).expanduser().resolve()
    click.echo(f"→ restoring from {src}", err=True)
    with tarfile.open(src, "r:gz") as tar:
        # SECURITY: Validate every member before extraction (defends against path traversal)
        for member in tar.getmembers():
            # Reject absolute paths, parent references, hard links, special files
            if member.name.startswith("/") or ".." in member.name.split("/"):
                raise click.ClickException(
                    f"Refusing to extract member with unsafe name: {member.name!r}"
                )
            if member.issym() or member.islnk():
                raise click.ClickException(
                    f"Refusing to extract symlink/hardlink: {member.name!r}"
                )
            if not (member.isfile() or member.isdir()):
                raise click.ClickException(
                    f"Refusing to extract non-regular member: {member.name!r}"
                )
        # Extract to a temp dir, then move files to their destinations
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tar.extractall(tmp)  # nosec B202 — validated above
            # Move DB
            for db_file in (Path(tmp) / "db").glob("*.db"):
                target = default_db_path()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(db_file), str(target))
                click.echo(f"  ✓ restored db → {target}", err=True)
            # Restore config
            cfg_src = Path(tmp) / "config"
            if cfg_src.exists():
                cfg_target = Path.home() / ".config" / "project-mri"
                cfg_target.mkdir(parents=True, exist_ok=True)
                for f in cfg_src.iterdir():
                    shutil.move(str(f), str(cfg_target / f.name))
                click.echo(f"  ✓ restored config → {cfg_target}", err=True)
    click.echo("✓ restore complete", err=True)


# ---------------------------------------------------------------------------
# mri reset — wipe everything
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--keep-clones", is_flag=True, help="Don't delete cached clones")
def reset(yes: bool, keep_clones: bool) -> None:
    """Wipe the database, settings, and (optionally) cached clones."""
    from mri.config import get_config
    from mri.db.repository import default_db_path

    if not yes:
        click.confirm(
            "  This will DELETE all scans, projects, and settings. Continue?",
            abort=True,
        )

    db_path = default_db_path()
    if db_path.exists():
        db_path.unlink()
        click.echo(f"  ✓ deleted database at {db_path}", err=True)

    cfg = get_config()
    cache_dir = cfg.get("clones", {}).get("cache_dir")
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "project-mri" / "repos"
    cache_dir = Path(cache_dir)
    if not keep_clones and cache_dir.exists():
        shutil.rmtree(cache_dir)
        click.echo(f"  ✓ deleted clones cache at {cache_dir}", err=True)

    click.echo("✓ reset complete. Run `mri init` to set up again.", err=True)


# ---------------------------------------------------------------------------
# mri upgrade — pull latest and migrate
# ---------------------------------------------------------------------------


@cli.command()
def upgrade() -> None:  # nosec B404  # subprocess needed for pip
    """Upgrade the package to the latest version and run migrations."""
    import subprocess  # nosec B404
    click.echo("→ upgrading project-mri via pip", err=True)
    result = subprocess.run(  # nosec B603  # fixed args, no shell
        [sys.executable, "-m", "pip", "install", "--upgrade", "project-mri"],
        capture_output=False,
    )
    if result.returncode != 0:
        click.echo("✗ upgrade failed", err=True)
        sys.exit(1)
    click.echo("✓ upgrade complete (no migrations needed for v0.3.x)", err=True)


# ---------------------------------------------------------------------------
# mri ui — open dashboard in browser
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
@click.option("--no-serve", is_flag=True, help="Don't start the server, just open browser")
def ui(host: str | None, port: int | None, no_serve: bool) -> None:
    """Open the dashboard in your browser."""
    from mri.config import get_config
    cfg = get_config()
    if host is None:
        host = cfg.get("server", {}).get("host", "127.0.0.1")
    if port is None:
        port = cfg.get("server", {}).get("port", 7331)
    url = f"http://{host}:{port}/dashboard/"

    import threading
    import time
    import webbrowser

    def _open_later():
        time.sleep(2)
        webbrowser.open(url)

    if not no_serve:
        threading.Thread(target=_open_later, daemon=True).start()
        click.echo(f"→ opening {url}", err=True)
        serve.callback(host=host, port=port, reload=False)  # type: ignore[attr-defined]
    else:
        click.echo(f"  Open: {url}", err=True)
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# mri list — list scans
# ---------------------------------------------------------------------------


@cli.command(name="list")
@click.option("--limit", type=int, default=20, help="Max number of scans to show")
@click.option("--project", default=None, help="Filter by project path")
def list_cmd(limit: int, project: str | None) -> None:
    """List recent scans in the local database."""
    import sqlite3

    from mri.db.repository import _SCHEMA_PATH, default_db_path

    db = default_db_path()
    if not db.exists():
        click.echo("  (no scans yet — run `mri scan <path>` first)", err=True)
        return
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        if project:
            cur = conn.execute(
                """
                SELECT s.scan_uuid, s.status, s.started_at, s.finished_at,
                       p.name AS project_name, p.path AS project_path
                FROM scans s
                JOIN projects p ON p.id = s.project_id
                WHERE p.path = ?
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (project, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT s.scan_uuid, s.status, s.started_at, s.finished_at,
                       p.name AS project_name, p.path AS project_path
                FROM scans s
                JOIN projects p ON p.id = s.project_id
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cur.fetchall()
        if not rows:
            click.echo("  (no scans yet)", err=True)
            return
        click.echo(f"  {len(rows)} recent scan(s):", err=True)
        click.echo("", err=True)
        for r in rows:
            uuid = (r["scan_uuid"] or "")[:8] or "--------"
            started = (r["started_at"] or "")[:19]
            status = r["status"]
            name = r["project_name"] or "?"
            click.echo(f"  {uuid}  {status:9s}  {started}  {name}", err=True)
    finally:
        conn.close()


if __name__ == "__main__":
    cli()
