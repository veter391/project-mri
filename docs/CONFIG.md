# Configuration reference

project-mri reads configuration from three sources, in order of precedence
(higher wins):

1. **Environment variables** (`MRI_*`)
2. **`.mri.yml`** file (default: `~/.config/project-mri/.mri.yml`)
3. **Built-in defaults** (compiled into the binary)

The full schema:

```yaml
# .mri.yml

server:
  host: 127.0.0.1          # bind address (use 0.0.0.0 for all interfaces)
  port: 7331                # port
  workers: 1                # uvicorn workers (single-user, keep at 1)
  log_level: INFO           # DEBUG | INFO | WARNING | ERROR
  log_format: text          # text | json
  cors_origins: []          # list of allowed origins (empty = deny)
  allowed_roots: []         # path allowlist for scans (empty = any path)
  api_keys: []              # legacy API keys (empty = auth disabled)
  rate_limit: 60            # requests/min/IP (general)
  scan_rate_limit: 5        # POST /api/scans/min/IP
  max_request_bytes: 1048576  # 1 MiB request body cap

database:
  path: ~/.cache/project-mri/mri.db

scans:
  max_concurrent: 4         # parallel scans (single-user, 4 is plenty)
  default_depth: 1          # clone depth for URL scans
  cleanup_clones: true      # remove clone dir after scan
  timeout_seconds: 600      # hard limit per scan

analyzers:
  health:
    enabled: true
  architecture:
    enabled: true
  dependencies:
    enabled: true
    max_modules: 10000
  complexity:
    enabled: true
    max_cyclomatic: 50
  tech_debt:
    enabled: true
    max_file_bytes: 1000000  # skip very large files
  coupling:
    enabled: true
  git_history:
    enabled: true
    max_commits: 5000

auth:
  jwt_secret: ""             # auto-generated on first run, stored in DB
  jwt_ttl_seconds: 86400     # 24h
  session_cookie_name: mri_session
  cookie_secure: false       # set true behind HTTPS

integrations:
  github:
    token: ""               # ghp_xxx
  gitlab:
    token: ""               # glpat-xxx
    url: https://gitlab.com
  bitbucket:
    token: ""

notifications:
  webhook:
    url: ""                 # single URL
    headers: {}             # extra headers
    secret: ""              # HMAC-SHA256 signing secret
    events:
      - scan.completed
      - scan.failed

clones:
  cache_dir: ~/.cache/project-mri/repos
  keep_clones: false

watch:
  debounce_seconds: 2       # wait this long after last file change
  globs:                    # which files to watch
    - "**/*.py"
    - "**/*.js"
    - "**/*.ts"
    - "**/*.go"
    - "**/*.rs"
  ignore:
    - "**/.git/**"
    - "**/node_modules/**"
    - "**/__pycache__/**"

dashboard:
  enabled: true
  title: "project-mri"
  accent_color: "#F4A847"
  shortcuts: false
```

---

## Environment variable reference

All env vars are prefixed with `MRI_`. They override `.mri.yml` values.

| Env var | YAML equivalent | Example |
|---|---|---|
| `MRI_HOST` | `server.host` | `0.0.0.0` |
| `MRI_PORT` | `server.port` | `8080` |
| `MRI_LOG_LEVEL` | `server.log_level` | `DEBUG` |
| `MRI_LOG_FORMAT` | `server.log_format` | `json` |
| `MRI_CORS_ORIGINS` | `server.cors_origins` | `https://app.example.com,https://other.example.com` |
| `MRI_ALLOWED_ROOTS` | `server.allowed_roots` | `/home/me/code,/work` |
| `MRI_API_KEYS` | `server.api_keys` | `secret1,secret2` |
| `MRI_RATE_LIMIT` | `server.rate_limit` | `120` |
| `MRI_SCAN_RATE_LIMIT` | `server.scan_rate_limit` | `10` |
| `MRI_MAX_REQUEST_BYTES` | `server.max_request_bytes` | `2097152` |
| `MRI_DB` | `database.path` | `/var/lib/mri/mri.db` |
| `MRI_CONFIG` | (config file path) | `/etc/mri/config.yml` |
| `MRI_GITHUB_TOKEN` | `integrations.github.token` | `ghp_xxx` |
| `MRI_GITLAB_TOKEN` | `integrations.gitlab.token` | `glpat-xxx` |
| `MRI_GITLAB_URL` | `integrations.gitlab.url` | `https://gitlab.mycorp.com` |
| `MRI_BITBUCKET_TOKEN` | `integrations.bitbucket.token` | `xxx` |
| `MRI_WEBHOOK_URL` | `notifications.webhook.url` | `https://hooks.slack.com/...` |
| `MRI_WEBHOOK_SECRET` | `notifications.webhook.secret` | `xxx` |
| `MRI_COOKIE_SECURE` | `auth.cookie_secure` | `true` |

---

## Section reference

### `server`

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | `127.0.0.1` | Bind address |
| `port` | int | `7331` | Port |
| `workers` | int | `1` | Uvicorn workers (don't change for single-user) |
| `log_level` | enum | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `log_format` | enum | `text` | `text` (dev) or `json` (prod) |
| `cors_origins` | list | `[]` | Allowed origins; empty = deny all |
| `allowed_roots` | list | `[]` | Scan path allowlist; empty = any path |
| `api_keys` | list | `[]` | Legacy API keys; empty = auth disabled (JWT still works) |
| `rate_limit` | int | `60` | General requests/min/IP |
| `scan_rate_limit` | int | `5` | Scans/min/IP |
| `max_request_bytes` | int | `1048576` | 1 MiB body cap |

### `database`

| Key | Type | Default | Description |
|---|---|---|---|
| `path` | path | `~/.cache/project-mri/mri.db` | SQLite database file |

### `scans`

| Key | Type | Default | Description |
|---|---|---|---|
| `max_concurrent` | int | `4` | Parallel scans |
| `default_depth` | int | `1` | Clone depth for URL scans |
| `cleanup_clones` | bool | `true` | Remove clone dir after scan |
| `timeout_seconds` | int | `600` | Hard limit per scan (10 min default) |

### `analyzers`

Each analyzer has its own `enabled` boolean and analyzer-specific thresholds.
See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for analyzer internals.

| Analyzer | Specific knobs |
|---|---|
| `health` | (just enabled) |
| `architecture` | (just enabled) |
| `dependencies` | `max_modules` |
| `complexity` | `max_cyclomatic` |
| `tech_debt` | `max_file_bytes` |
| `coupling` | (just enabled) |
| `git_history` | `max_commits` |

### `auth`

| Key | Type | Default | Description |
|---|---|---|---|
| `jwt_secret` | string | (auto) | Auto-generated on first run, stored in DB |
| `jwt_ttl_seconds` | int | `86400` | JWT lifetime (24h) |
| `session_cookie_name` | string | `mri_session` | Cookie name |
| `cookie_secure` | bool | `false` | Set true behind HTTPS |

### `integrations`

PAT tokens for cloning private repos. See [INTEGRATIONS.md](./INTEGRATIONS.md).

### `notifications`

Single webhook URL with optional HMAC signing. See [INTEGRATIONS.md](./INTEGRATIONS.md).

For multiple webhooks or per-event routing, use the API to register them
programmatically.

### `clones`

| Key | Type | Default | Description |
|---|---|---|---|
| `cache_dir` | path | `~/.cache/project-mri/repos` | Where cloned repos live |
| `keep_clones` | bool | `false` | Don't remove after scan |

### `watch`

Settings for `mri watch`. See `mri watch --help`.

### `dashboard`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Disable to return 404 on /dashboard |
| `title` | string | `project-mri` | Browser tab title |
| `accent_color` | string | `#F4A847` | Hex accent color |
| `shortcuts` | bool | `false` | Enable keyboard shortcuts |

---

## Minimal config

The smallest valid `.mri.yml`:

```yaml
# All defaults are fine — no need to write this file unless overriding
```

## Strict production config

For a public-facing deployment behind a reverse proxy:

```yaml
server:
  host: 127.0.0.1
  port: 7331
  log_level: WARNING
  log_format: json
  cors_origins:
    - https://mri.yourcompany.com
  allowed_roots:
    - /srv/repos
  api_keys: []           # JWT-only
  rate_limit: 30
  scan_rate_limit: 2

database:
  path: /var/lib/mri/mri.db

auth:
  cookie_secure: true

dashboard:
  enabled: true
```

---

## Schema validation

On startup, project-mri validates your `.mri.yml` against the schema. If there's
a typo or invalid value, you'll get:

```
ERROR  Invalid config at /home/me/.config/project-mri/.mri.yml:
  server.port: expected int, got "seven thousand three hundred"
```

Fix the value or remove the file to use defaults.

---

## Reloading

Config is loaded once at startup. To pick up changes:

```bash
# If running under systemd:
sudo systemctl restart project-mri

# If running in foreground:
# Ctrl+C, then `mri serve` again

# If running in Docker:
docker restart project-mri
```

For most settings, you don't need to restart between changes — they're read at startup.
Watch mode and live scan settings are applied per-scan.