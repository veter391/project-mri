"""`mri` CLI — subcommands: init, scan, fusion, eval, mcp, serve, watch, demo, backup, restore, upgrade, reset, ui."""
from __future__ import annotations

import getpass
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

# Everything heavy is imported inside the command that needs it. Importing the
# scanner, uvicorn, GitPython and the demo feed at module scope cost 650 ms on
# every invocation — including `--help`, `--version`, shell completion and every
# error path — against a 49 ms floor for click alone. A CLI that takes half a
# second to print usage is a CLI that feels broken.


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

    # Writing the file is not the same as it being used. The loader searches a
    # fixed list of locations, so a custom path is silently ignored unless it
    # happens to be one of them or MRI_CONFIG points at it. Saying "config
    # written" and then never reading it is worse than refusing outright.
    from mri.config import is_discoverable

    if not is_discoverable(cfg_path):
        click.echo(
            f"  ! {cfg_path} is not one of the locations project-mri looks in.\n"
            f"    Set MRI_CONFIG to use it:  export MRI_CONFIG={cfg_path}",
            err=True,
        )

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
    import asyncio

    from mri.services.report_generator import render_json, write_report_files
    from mri.services.scanner import Scanner, ScanOptions

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
        # Move to the user-specified path. Use replace(), not rename(): on Windows
        # Path.rename raises FileExistsError when the target already exists, so a
        # second `mri scan` to the same output path would crash. replace() is the
        # atomic cross-platform overwrite.
        if str(out) != str(files["html"]):
            files["html"].replace(out)
        if json_out:
            Path(json_out).write_text(render_json(report), encoding="utf-8")

        # Record it, so `mri list` and the dashboard see CLI scans too. Without
        # this the CLI wrote a file and nothing else, and the documented
        # "scan then list" pairing could never work.
        from mri.db.repository import persist_report

        persist_report(report)

        click.echo(f"✓ report saved → {out}", err=True)
        click.echo(f"  overall health: {report.overall_health:.1f}/100 ({report.overall_band})", err=True)
        click.echo(f"  duration: {report.duration_ms} ms", err=True)
        click.echo(f"  findings: {len(report.findings)}", err=True)

    asyncio.run(go())


# ---------------------------------------------------------------------------
# mri fusion — fuse agent provenance onto a scanned repo
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--top", default=10, type=int, help="How many risky files to explain")
@click.option(
    "--store-content", is_flag=True,
    help="Retain agent prompt/response text (off by default; logs can hold secrets)",
)
@click.option("--json-out", default=None, help="Write the fusion report as JSON to this path")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
def fusion(project_path: str, top: int, store_content: bool, json_out: str | None, quiet: bool) -> None:
    """Fuse agent sessions, decisions and consequences onto a scanned repo.

    Reads local agent session logs, links them to the commits they produced,
    computes per-file AI/human/unattributed authorship, mines decisions from
    ADRs and commits, and explains the repo's riskiest files — the files your
    last `mri scan` flagged. Run `mri scan <path>` first so there are hotspots
    to explain.
    """
    import asyncio

    click.echo(f"→ fusing agent provenance onto {project_path}", err=True)

    async def go() -> None:
        import git

        from mri.db.repository import get_connection, top_risk_files, upsert_project
        from mri.fusion import run_fusion

        root = Path(project_path).resolve()
        try:
            repo = git.Repo(root)
        except Exception:  # noqa: BLE001 - any GitPython error means "not a usable repo"
            click.echo(f"✗ {root} is not a git repository", err=True)
            sys.exit(1)

        adr_dir = root / "docs" / "adr"
        async with get_connection() as conn:
            project_id = await upsert_project(
                conn, path=str(root), name=root.name, default_branch="HEAD"
            )
            hotspots = await top_risk_files(conn, project_id, limit=top)
            if not hotspots and not quiet:
                click.echo(
                    "  ! no scored files found — run `mri scan` first to get hotspots to explain",
                    err=True,
                )

            report = await run_fusion(
                conn, repo, root, project_id=project_id,
                hotspots=hotspots or None,
                adr_dir=adr_dir if adr_dir.is_dir() else None,
                store_content=store_content,
            )

        if not quiet:
            click.echo(
                f"  sessions: {report.ingest.sessions} · touches: {report.ingest.touches} · "
                f"correlated: {report.correlation.linked} → {len(report.correlation.commits)} commits",
                err=True,
            )
            click.echo(
                f"  decisions: {report.adrs} ADR + {report.commits} commit · "
                f"cross-links: {report.decision_links} · files authored: {report.authored_files}",
                err=True,
            )

        for exp in report.explanations:
            click.echo(exp.prose)

        if json_out:
            from mri.models.cli_json import (
                FusionCorrelationJson,
                FusionDecisionsJson,
                FusionFactorJson,
                FusionFileJson,
                FusionIngestJson,
                FusionJson,
            )

            payload = FusionJson(
                ingest=FusionIngestJson(
                    sessions=report.ingest.sessions, touches=report.ingest.touches
                ),
                correlation=FusionCorrelationJson(
                    linked=report.correlation.linked, commits=len(report.correlation.commits)
                ),
                decisions=FusionDecisionsJson(
                    adr=report.adrs, commit=report.commits, cross_links=report.decision_links
                ),
                authored_files=report.authored_files,
                files=[
                    FusionFileJson(
                        file=e.file_path, prose=e.prose,
                        factors=[FusionFactorJson(name=f.name, value=f.value) for f in e.factors],
                    )
                    for e in report.explanations
                ],
            )
            Path(json_out).write_text(payload.model_dump_json(indent=2), encoding="utf-8")
            if not quiet:
                click.echo(f"  ✓ JSON → {json_out}", err=True)

    asyncio.run(go())


# ---------------------------------------------------------------------------
# mri eval — validate the fusion numbers against known ground truth
# ---------------------------------------------------------------------------


@cli.command("eval")
@click.option("--json-out", default=None, help="Write the eval report as JSON to this path")
def eval_cmd(json_out: str | None) -> None:
    """Run the evaluation harness: calibrate the fusion numbers against a labeled
    corpus and assert the product never over-claims.

    Builds scenarios whose true AI-authorship is known, runs the whole fusion
    loop over them, and reports the error between computed and true shares plus
    the over-claim guard. Exits non-zero if any share drifts past tolerance or
    any honesty invariant is violated — this is the hard gate.
    """
    import asyncio

    async def go() -> None:
        from mri.eval import run_eval

        report = await run_eval()

        click.echo(f"eval corpus: {report.case}", err=True)
        for path, (expected, computed, err) in sorted(report.calibration.items()):
            mark = "ok" if err <= 2.0 else "OFF"
            click.echo(f"  [{mark}] {path:16} truth={expected:5.1f}%  computed={computed:5.1f}%  err={err:.2f}")
        click.echo(f"  correlation recall: {report.correlation_recall:.2f}", err=True)
        click.echo(f"  over-claim violations: {len(report.violations)}", err=True)
        for v in report.violations:
            click.echo(f"    ✗ {v.rule}: {v.detail} ({v.ref})", err=True)

        if json_out:
            from mri.models.cli_json import CalibrationEntryJson, EvalJson, ViolationJson

            payload = EvalJson(
                case=report.case,
                calibration={
                    p: CalibrationEntryJson(expected=e, computed=c, error=err)
                    for p, (e, c, err) in report.calibration.items()
                },
                correlation_recall=report.correlation_recall,
                consequence_false_positive_rate=report.consequence_false_positive_rate,
                violations=[
                    ViolationJson(rule=v.rule, detail=v.detail, ref=v.ref)
                    for v in report.violations
                ],
                passed=report.passed,
            )
            Path(json_out).write_text(payload.model_dump_json(indent=2), encoding="utf-8")

        if report.passed:
            click.echo("✓ eval passed: numbers calibrated, no over-claim", err=True)
        else:
            click.echo("✗ eval FAILED", err=True)
            sys.exit(1)

    asyncio.run(go())


# ---------------------------------------------------------------------------
# mri mcp — serve MRI as an agent-native MCP provider (stdio)
# ---------------------------------------------------------------------------


@cli.command()
def mcp() -> None:
    """Serve MRI's fusion tools to coding agents over MCP (stdio transport).

    Exposes fuse_project, explain_file, get_authorship, get_decisions and
    get_consequences so an agent can ask who authored a file, what decided it,
    and what changed after — mid-task. Needs the optional MCP dependency:
    `pip install project-mri[mcp]`.
    """
    # build_server defers the optional `mcp` import, so a missing dependency
    # surfaces as a ModuleNotFoundError here, not at module import time.
    from mri.mcp_server import build_server

    try:
        server = build_server()
    except ModuleNotFoundError as e:
        click.echo(f"✗ {e}", err=True)
        sys.exit(1)

    click.echo("→ project-mri MCP server on stdio (Ctrl+C to stop)", err=True)
    server.run(transport="stdio")


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
    import asyncio

    from mri.services.report_generator import render_html, render_json
    from mri.services.scanner import Scanner, ScanOptions

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
    # Fail closed: never expose an unauthenticated server on a public interface.
    from mri.security import assert_safe_bind
    try:
        assert_safe_bind(host)
    except RuntimeError as exc:
        raise SystemExit(f"error: {exc}") from exc
    import uvicorn

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
    from mri.services.demo_feed import generate_demo_report
    from mri.services.report_generator import render_html

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

    # Apply schema migrations in a fresh interpreter: this process still has the
    # pre-upgrade code (and therefore the old migration files) imported.
    click.echo("→ applying schema migrations", err=True)
    migrated = subprocess.run(  # nosec B603  # fixed args, no shell
        [sys.executable, "-m", "mri.cli", "db", "upgrade"],
        capture_output=False,
    )
    if migrated.returncode != 0:
        click.echo("✗ schema migration failed — the database is unchanged", err=True)
        sys.exit(1)
    click.echo("✓ upgrade complete", err=True)


# ---------------------------------------------------------------------------
# mri openapi — dump the API schema (used to generate typed clients)
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--output", "-o", default=None, help="Write to this file instead of stdout")
def openapi(output: str | None) -> None:
    """Print the OpenAPI schema for the HTTP API."""
    import json as _json

    from mri.api.app import create_app

    spec = _json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(spec, encoding="utf-8")
        click.echo(f"✓ wrote {output}", err=True)
    else:
        click.echo(spec, nl=False)


# ---------------------------------------------------------------------------
# mri db — inspect and migrate the local database
# ---------------------------------------------------------------------------


@cli.group()
def db() -> None:
    """Inspect and migrate the local database."""


@db.command("upgrade")
def db_upgrade() -> None:
    """Apply any pending schema migrations."""
    from mri.db.migrator import MigrationError, migrate
    from mri.db.repository import default_db_path

    path = default_db_path()
    try:
        applied = migrate(path)
    except MigrationError as exc:
        click.echo(f"✗ {exc}", err=True)
        click.echo("  the database was left unchanged", err=True)
        sys.exit(1)
    if applied:
        for name in applied:
            click.echo(f"  applied {name}", err=True)
        click.echo(f"✓ {len(applied)} migration(s) applied", err=True)
    else:
        click.echo("✓ schema is up to date", err=True)


@db.command("status")
def db_status() -> None:
    """Show which migrations have been applied and which are pending."""
    from mri.db.migrator import applied_migrations, pending_migrations
    from mri.db.repository import default_db_path

    path = default_db_path()
    click.echo(f"database: {path}")
    if not path.exists():
        click.echo("  (not created yet — it is created on first use)")
        return
    for name in sorted(applied_migrations(path)):
        click.echo(f"  applied  {name}")
    pending = pending_migrations(path)
    for name in pending:
        click.echo(f"  PENDING  {name}")
    if not pending:
        click.echo("schema is up to date")


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
        serve_callback = serve.callback
        if serve_callback is None:  # pragma: no cover - a decorated command always has one
            raise RuntimeError("serve command has no callback")
        serve_callback(host=host, port=port, reload=False)
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

    from mri.db.migrator import migrate
    from mri.db.repository import connect_sync, default_db_path

    db = default_db_path()
    if not db.exists():
        click.echo("  (no scans yet — run `mri scan <path>` first)", err=True)
        return
    migrate(db)
    conn = connect_sync(db)
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
