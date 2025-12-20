# Project MRI — Backend

Local-first codebase intelligence. 6 analyzers, explainable scores, self-contained HTML reports.

## Why Python + FastAPI

We chose **Python 3.10+** because:

- **Tree-sitter** has rock-solid Python bindings for 30+ languages
- **GitPython** wraps libgit2 with a clean async-friendly API
- **FastAPI** gives us async, automatic OpenAPI/Swagger docs, and Pydantic v2 validation for free
- **aiosqlite** for non-blocking SQLite (WAL mode)
- **Jinja2** for the report HTML template
- Everything runs in the sandbox without external services

Go was tempting (compiled binary, no venv) but its tree-sitter bindings are
less mature and the sandbox can't execute the compiler.

## Install

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
```

Or with the published package:

```bash
pip install project-mri
```

## CLI

```bash
# Scan a repo → self-contained HTML report
mri scan /path/to/repo --output ./mri-report.html

# Run the HTTP API server
mri serve --port 7331
# → API at http://127.0.0.1:7331/api/docs

# Generate a demo report (no repo needed)
mri demo --output ./demo-report.html

# Run + open UI
mri ui --open
```

## HTTP API

After `mri serve`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Server health + version |
| `/api/version` | GET | Version + Python version |
| `/api/scans` | POST | Start a scan (`{project_path, branch?}`) → `{scan_uuid, stream_url}` |
| `/api/scans/{uuid}` | GET | Scan status + report (when done) |
| `/api/scans` | GET | List all scans |
| `/api/projects` | GET | List cached projects |
| `/api/scans/{uuid}/report.html` | GET | Self-contained HTML report |
| `/api/scans/{uuid}/report.json` | GET | Raw report JSON |
| `/api/demo/scan` | GET | Synthetic demo report (no repo needed) |
| `/api/demo/report.html` | GET | Synthetic HTML report |
| `/api/demo/feed` | GET | CLI-style progress feed lines |
| `/ws/scans/{uuid}` | WS | Live progress events |

OpenAPI docs at `/api/docs` (Swagger UI) or `/api/redoc`.

## Architecture

```
backend/
├── mri/
│   ├── api/
│   │   ├── app.py            # FastAPI factory
│   │   ├── deps.py           # DI (db session)
│   │   └── routes/
│   │       ├── health.py     # /api/health, /api/version
│   │       ├── scans.py      # POST/GET scans + WebSocket
│   │       └── demo.py       # Synthetic demo data
│   ├── analyzers/            # 6 analyzers — pure async units
│   │   ├── base.py           # BaseAnalyzer + Finding/Score models
│   │   ├── git_history.py    # Hotspots, bus factor, knowledge islands
│   │   ├── architecture.py   # Module map, depth, god modules
│   │   ├── dependencies.py   # Import graph + Tarjan cycle detection
│   │   ├── complexity.py     # LOC, function length, comment ratio
│   │   ├── tech_debt.py      # TODO/FIXME/HACK markers
│   │   └── coupling.py       # Robert Martin's I/A/D metrics
│   ├── services/
│   │   ├── scanner.py        # Orchestrator — runs all 6 analyzers
│   │   ├── report_generator.py  # Report → HTML/JSON via Jinja2
│   │   └── demo_feed.py      # Deterministic synthetic demo data
│   ├── models/
│   │   └── scan.py           # Pydantic v2 models (Finding, Score, Report)
│   ├── db/
│   │   ├── schema.sql        # SQLite schema (projects, scans, runs, findings)
│   │   └── repository.py     # async CRUD via aiosqlite
│   ├── templates/
│   │   └── report.html.j2    # Self-contained report template
│   └── cli.py                # Click CLI: scan / serve / demo / ui
├── tests/                    # pytest + pytest-asyncio
├── pyproject.toml
├── requirements.txt
└── README.md
```

## The 6 analyzers

Every analyzer is an async class with one job: compute `Findings` + a named
`Score` with a `contributors` ledger explaining the value. No black boxes.

### 1. `git_history` — `history_health`
Parses git log to find:
- **Hotspots**: files with most commits + churn
- **Bus factor**: minimum authors covering 80% of changes (1 = catastrophic, 5+ = healthy)
- **Knowledge islands**: files touched by only 1 author across ≥5 commits

### 2. `architecture` — `architecture_health`
Walks the filesystem, builds a module map (top-level dirs → files).
- **God modules**: any module with >40% of total LOC
- **Deep nesting**: paths deeper than 4 levels

### 3. `dependencies` — `dependency_health`
Parses imports via tree-sitter (Python, JS, TS, Go, Rust, Java) with regex
fallback. Builds a module-level dependency graph and runs **Tarjan's SCC**
to detect cycles. Top fan-in modules flagged as god consumers.

### 4. `complexity` — `complexity_health`
- File LOC distribution (flags >500 / >1500)
- Function length via tree-sitter AST walk (flags >60 lines)
- Comment ratio

### 5. `tech_debt` — `debt_index`
Counts weighted TODO/FIXME/HACK/XXX/BUG/DEPRECATED markers across files.
Density measured per kLOC. Files with ≥5 markers flagged as debt hotspots.

### 6. `coupling` — `coupling_health`
Robert Martin's I/A/D metrics per module:
- **Ca** (afferent coupling) — how many depend on this module
- **Ce** (efferent coupling) — how many this module depends on
- **I = Ce / (Ca + Ce)** — instability (0=stable, 1=unstable)
- **D = |A + I − 1| / √2** — distance from main sequence
- **Painful**: stable + concrete + high fan-in (high D, low I, low A)

### Overall health (weighted average)

| Score | Weight |
|-------|--------|
| architecture_health | 1.2 (architecture matters most) |
| history_health | 1.0 |
| dependency_health | 1.0 |
| complexity_health | 1.0 |
| debt_index | 1.0 |
| coupling_health | 0.9 |

The composition is recorded verbatim in `Report.composition` so the UI can
show "how this score is composed" — every number traces back to a signal.

## Storage

SQLite at `~/.cache/project-mri/mri.db` (override with `MRI_DB=...`).

Schema:
- `projects` — every scanned repo
- `scans` — every scan run
- `analyzer_runs` — per-analyzer results (signals + findings + score)
- `findings` — flattened per-finding rows for query/filter
- `scan_events` — audit trail (progress events, logs, errors)

WAL mode for concurrent reads while a scan writes.

## Running the tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

21 tests covering:
- Each analyzer's happy path + edge cases
- Cycle detection in the dependency graph
- Debt marker counting
- End-to-end scan via FastAPI TestClient
- Demo feed determinism

## Privacy

- No external network calls during a scan
- The report HTML is fully self-contained (no CDN, no analytics, no tracking)
- The DB is local SQLite — your data never leaves your machine
- Open source (MIT) — audit the code

## License

MIT. The core engine is MIT-licensed forever. Commercial features (managed
hosting, enterprise SSO) will live on top of the open core, never instead of it.