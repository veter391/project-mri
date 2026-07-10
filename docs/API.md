# HTTP API reference

project-mri ships with a FastAPI HTTP API. The same API is used by the dashboard and
the CLI — if the CLI can do it, the API can do it.

- **Default URL**: `http://localhost:7331`
- **OpenAPI schema**: `GET /openapi.json`
- **Interactive docs**: `GET /docs` (Swagger UI) and `GET /redoc`

---

## Authentication

Two ways to authenticate:

1. **JWT** (preferred) — get a token via `POST /api/auth/login`, send it as
   `Authorization: Bearer <token>`
2. **API key** (legacy) — set `MRI_API_KEYS=key1,key2` env var, send any key as
   `Authorization: Bearer <key>` or `X-API-Key: <key>`

If `MRI_API_KEYS` is empty, no auth is required for API endpoints. The dashboard still
needs the JWT login flow.

---

## Endpoints

### Health

#### `GET /api/health`

Liveness probe. Always returns 200 if the process is up.
```json
{"status": "ok"}
```

#### `GET /api/health/deep`

Readiness probe. Checks DB, all analyzers, tree-sitter, git.
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "analyzers": "ok",
    "tree_sitter": "ok",
    "git": "ok"
  }
}
```

#### `GET /api/version`

```json
{"version": "0.3.0"}
```

---

### Auth

#### `POST /api/auth/login`

```bash
curl -X POST http://localhost:7331/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}'
```
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {"id": 1, "username": "admin", "created_at": "...", "last_login_at": "..."},
  "expires_in": 86400
}
```

#### `POST /api/auth/logout`

Clears the session cookie. JWTs are stateless and cannot be revoked server-side
(except by rotating the secret, which logs out all users).

#### `GET /api/auth/whoami`

Requires auth. Returns current user.
```json
{"id": 1, "username": "admin", "created_at": "...", "last_login_at": "..."}
```

#### `POST /api/auth/change-password`

```bash
curl -X POST http://localhost:7331/api/auth/change-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"old","new_password":"new"}'
```

#### `GET /api/auth/status`

Public. Tells whether the app has been initialized.
```json
{"initialized": true, "user_count": 1}
```

---

### Scans

#### `POST /api/scans`

Start a scan.

```bash
curl -X POST http://localhost:7331/api/scans \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_path":"/path/to/repo","branch":"main","depth":1}'
```

Request body:
| Field | Type | Required | Description |
|---|---|---|---|
| `project_path` | string | yes | Absolute local path or git URL |
| `branch` | string | no | Git branch to checkout (URL scans only) |
| `depth` | int | no | Clone depth (default: 1 = shallow) |
| `cleanup_clone` | bool | no | Remove clone after scan (default: true) |

Response (202):
```json
{
  "scan_uuid": "abc123...",
  "project_name": "myrepo",
  "project_path": "/path/to/repo",
  "status": "queued",
  "started_at": "2025-01-15T10:30:00Z",
  "stream_url": "/api/ws/scans/abc123..."
}
```

#### `GET /api/scans`

List recent scans.

| Query param | Default | Description |
|---|---|---|
| `limit` | 50 | Max results |
| `offset` | 0 | Pagination offset |
| `project` | (none) | Filter by exact project_path |
| `status` | (none) | Filter by status: queued/running/completed/failed/cancelled |

```json
{
  "scans": [
    {"scan_uuid": "abc...", "project_name": "...", "status": "completed", "started_at": "...", "duration_s": 1.23, "score": {"health": 78}}
  ],
  "total": 142
}
```

#### `GET /api/scans/{uuid}`

Get a single scan's status + report (if completed).

```json
{
  "scan_uuid": "abc...",
  "project_name": "myrepo",
  "project_path": "/path/to/repo",
  "status": "completed",
  "started_at": "...",
  "finished_at": "...",
  "duration_s": 1.23,
  "report": {
    "overall_score": {"score": 78, "band": "good"},
    "analyzers": {
      "health": {"score": 78, ...},
      "architecture": {"score": 65, ...},
      ...
    },
    "findings": [...],
    "stats": {"files": 42, "loc": 3500, ...}
  }
}
```

#### `DELETE /api/scans/{uuid}`

Idempotent delete. Removes the scan record + its reports from disk.

Returns 204 on success (or already-deleted). Returns 404 if UUID doesn't match a scan
format.

#### `GET /api/scans/{uuid}/report.html`

Full HTML report (browser-friendly, ~10KB).

#### `GET /api/scans/{uuid}/report.json`

Full machine-readable report.

#### `GET /api/scans/{uuid}/report.sarif`

SARIF 2.1.0 export for GitHub Code Scanning / IDE integration. ~8KB.

#### `GET /api/scans/{a}/diff/{b}`

Compare two scans (a must be older than b).

```json
{
  "before": {
    "scan_uuid": "abc...",
    "started_at": "...",
    "finished_at": "...",
    "overall_health": 75.0,
    "overall_band": "good"
  },
  "after": {
    "scan_uuid": "def...",
    "started_at": "...",
    "finished_at": "...",
    "overall_health": 78.0,
    "overall_band": "good"
  },
  "score_diff": [
    {"label": "architecture_health", "before": 65, "after": 70, "delta": 5},
    {"label": "complexity_health", "before": 75, "after": 75, "delta": 0},
    ...
  ],
  "findings": {
    "added": [...],
    "removed": [...],
    "severity_changed": [...]
  },
  "stats_diff": {
    "file_count": 2,
    "loc_total": 200,
    "commit_count": 1
  }
}
```

`score_diff` is a list of `{label, before, after, delta}` for each analyzer
metric. `stats_diff` shows absolute deltas for files / LOC / commits.

#### `WS /api/ws/scans/{uuid}`

Real-time progress stream.

Events (server → client):
- `hello` — connection established, includes initial state
- `progress` — `{phase, detail, percent}` (0-100)
- `analyzer_started` — `{analyzer}`
- `analyzer_finished` — `{analyzer, duration_s, findings_count}`
- `log` — `{level, message}` (debug logs)
- `done` — final report (same as `GET /api/scans/{uuid}`)
- `error` — `{message}` (scan failed)
- `ping` — heartbeat (every 30s; client should reply with `pong`)

Send:
- `pong` — heartbeat reply
- `cancel` — request cancellation

Example with `websocat`:
```bash
websocat ws://localhost:7331/api/ws/scans/abc...
```

---

### Projects

#### `GET /api/projects`

List unique projects (deduped by path/URL).

```json
{
  "projects": [
    {
      "name": "myrepo",
      "path": "/path/to/repo",
      "scan_count": 12,
      "latest_scan": {"uuid": "...", "score": 78, "started_at": "..."}
    }
  ]
}
```

---

### Demo

#### `GET /api/demo/scan`

Returns a synthetic "completed" scan for demo / preview purposes.

#### `GET /api/demo/report.html`, `/report.json`, `/feed`

Synthetic reports.

---

### Metrics

#### `GET /metrics`

Prometheus text format. Includes:
- `mri_scans_total{status="..."}` — scan counter
- `mri_scan_duration_seconds` — histogram
- `mri_findings_total{analyzer,severity}` — finding counter
- `mri_api_requests_total{endpoint,status}` — request counter
- `process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_open_fds`
- `python_gc_*` — GC stats

Requires auth.

---

## Error responses

All errors return JSON:
```json
{"error": "human-readable message", "code": "validation_error"}
```

| Status | When |
|---|---|
| 400 | Bad input (validation failed) |
| 401 | Auth required / invalid token |
| 403 | Auth valid but forbidden (rare — only for admin-only endpoints) |
| 404 | Resource not found |
| 409 | Conflict (e.g., scan already running on same path) |
| 422 | Semantic validation failed (e.g., path doesn't exist) |
| 429 | Rate limited |
| 500 | Internal error |
| 503 | Service unavailable (e.g., during `mri upgrade`) |

Stack traces are never returned to clients — they're logged server-side only.

---

## CORS

By default, CORS is **deny**. To allow specific origins:
```bash
MRI_CORS_ORIGINS="https://myapp.example.com,https://other.example.com" mri serve
```

The dashboard is served from the same origin so it doesn't need CORS.

---

## Rate limits

| Endpoint | Limit |
|---|---|
| `POST /api/scans` | 5 / minute / IP |
| All other endpoints | 60 / minute / IP |

Configured via `MRI_SCAN_RATE_LIMIT` and `MRI_RATE_LIMIT` env vars.

---

## Pagination

List endpoints use offset/limit pagination:
```bash
curl 'http://localhost:7331/api/scans?limit=10&offset=20'
```

Response includes `total` for total count.

---

## Versioning

We follow [semver](https://semver.org/):
- **Major** versions may include breaking changes to the API
- **Minor** versions add features without breaking
- **Patch** versions are bug fixes only

Currently at **0.3.0** — the API is stable but may change in 1.0.