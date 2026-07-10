# Integrations

project-mri is self-hosted by default but integrates with the outside world in three ways:

1. **Repository cloning** — scan private GitHub / GitLab / Bitbucket repos via PAT
2. **Webhooks** — get notified when scans finish
3. **CI/CD** — run project-mri in GitHub Actions / GitLab CI as a quality gate

---

## 1. Repository cloning

### Public repos (no auth needed)

```bash
mri scan https://github.com/owner/public-repo.git
mri scan https://gitlab.com/owner/public-repo.git
```

project-mri does a shallow clone (`--depth 1`) into `~/.cache/project-mri/repos/`,
runs the scan, then cleans up unless `clones.keep_clones: true` in config.

### Private repos (PAT required)

#### GitHub

Create a Personal Access Token at <https://github.com/settings/tokens> with `repo` scope.

```bash
export MRI_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
mri scan https://github.com/owner/private-repo.git
```

The token is injected into the URL as `https://x-access-token:TOKEN@github.com/...`
and never logged.

#### GitLab

Create a Personal Access Token at <https://gitlab.com/-/user_settings/personal_access_tokens>
with `read_repository` scope.

```bash
export MRI_GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
export MRI_GITLAB_URL=https://gitlab.com  # default; set for self-hosted
mri scan https://gitlab.com/owner/private-repo.git
```

#### Bitbucket

Create an App Password at <https://bitbucket.org/account/settings/app-passwords/> with
`repository:read` scope.

```bash
export MRI_BITBUCKET_TOKEN=xxxxxxxxxxxxxxxxxxxx
mri scan https://bitbucket.org/owner/private-repo.git
```

#### SSH

If your repo is SSH-only (`git@github.com:owner/repo.git`):

```bash
# Make sure your SSH key is loaded
ssh-add ~/.ssh/id_ed25519

mri scan git@github.com:owner/repo.git
```

project-mri uses your existing SSH config — no special setup needed.

### Caching

Cloned repos are stored at `~/.cache/project-mri/repos/<sha256-of-url-prefix>/`.
To wipe the cache:

```bash
rm -rf ~/.cache/project-mri/repos
```

### Disable cleanup

If you want to keep the clone after the scan (for debugging):

```yaml
# .mri.yml
clones:
  keep_clones: true
```

Or per-scan:
```bash
curl -X POST http://localhost:7331/api/scans \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"project_path":"https://...","cleanup_clone":false}'
```

---

## 2. Webhooks

Configure one or more webhook URLs to be called when scans finish:

```yaml
# .mri.yml
notifications:
  webhook:
    url: https://your-app.example.com/webhooks/mri
    # Optional: custom headers (e.g., for auth)
    headers:
      X-Webhook-Secret: your-shared-secret
    # Optional: events to subscribe to
    events:
      - scan.completed
      - scan.failed
```

Or via env var (single URL):
```bash
export MRI_WEBHOOK_URL=https://your-app.example.com/webhooks/mri
```

### Event payload

```json
{
  "event": "scan.completed",
  "timestamp": "2025-01-15T10:30:00Z",
  "scan_uuid": "abc123...",
  "project_name": "myrepo",
  "project_path": "/path/to/repo",
  "status": "completed",
  "duration_s": 1.23,
  "score": {
    "overall": 78,
    "band": "good",
    "analyzers": {
      "health": 78,
      "architecture": 65,
      "dependencies": 80,
      "complexity": 72,
      "tech_debt": 60,
      "git_history": 85
    }
  },
  "findings_count": {
    "critical": 0,
    "high": 2,
    "medium": 5,
    "low": 12,
    "info": 18
  }
}
```

For `scan.failed`:
```json
{
  "event": "scan.failed",
  "scan_uuid": "abc...",
  "project_name": "myrepo",
  "error": "git clone failed: authentication required",
  "duration_s": 0.5
}
```

### Delivery

- project-mri retries on non-2xx with exponential backoff: 1s, 5s, 30s (max 3 attempts)
- All deliveries are logged in the `webhook_deliveries` table
- Sign requests with HMAC-SHA256 if `secret` is set:

```yaml
notifications:
  webhook:
    url: https://...
    secret: your-shared-secret
```

The server sends `X-MRI-Signature: sha256=<hex>` and `X-MRI-Timestamp: <unix>` headers.
Verify on the receiving end:

```python
import hmac, hashlib
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
if hmac.compare_digest(expected, signature_header.removeprefix("sha256=")):
    # valid
```

---

## 3. CI/CD

### GitHub Actions

Use the official project-mri action:

```yaml
# .github/workflows/mri.yml
name: project-mri
on: [push, pull_request]

jobs:
  mri:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: project-mri/mri-action@v1
        with:
          path: .
          upload-sarif: true
```

This:
1. Installs project-mri
2. Runs a scan on the current repo
3. Uploads the SARIF report to GitHub Code Scanning
4. Posts a summary comment on PRs

For private repos, add `permissions: contents: read` and provide the `MRI_GITHUB_TOKEN`
secret if scanning other repos.

#### Action reference

| Input | Default | Description |
|---|---|---|
| `path` | `.` | Path to scan |
| `branch` | (current) | Branch to scan |
| `output-dir` | `./mri-reports` | Where to write reports |
| `upload-sarif` | `true` | Upload SARIF to Code Scanning |
| `python-version` | `3.11` | Python version |

### GitLab CI

```yaml
# .gitlab-ci.yml
include:
  - remote: 'https://raw.githubusercontent.com/project-mri/project-mri/main/ci/gitlab-ci.yml'
```

This adds an `analyze` stage that:
1. Installs project-mri
2. Runs a scan
3. Uploads results as a Code Quality artifact (visible in MR widget)

### Pre-commit hook

```bash
# .git/hooks/pre-commit
#!/bin/sh
mri scan --json-out /tmp/mri-pre-commit.json .
if [ $? -ne 0 ]; then
  echo "❌ project-mri check failed. See /tmp/mri-pre-commit.json"
  exit 1
fi
```

Or scan only staged files:
```bash
git diff --cached --name-only | xargs mri scan-files
```

### Quality gate

Fail builds if health score drops below threshold:

```bash
SCORE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:7331/api/scans/$SCAN_UUID | \
  jq -r '.report.overall_score.score')

if [ "$SCORE" -lt 70 ]; then
  echo "❌ Health score $SCORE below threshold 70"
  exit 1
fi
```

---

## IDE integrations

### VS Code

Install the [SARIF Viewer extension](https://marketplace.visualstudio.com/items?itemName=MS-SarifVSCode.sarif-viewer).
Then in your project:
```bash
mri scan . --json-out .mri-report.json
python -c "
import json
# Convert JSON to SARIF (use the helper from our GitHub Action)
"
code .mri-report.sarif
```

Findings appear inline with severity indicators and "Go to file" links.

### JetBrains IDEs

Same workflow — IntelliJ Ultimate has built-in SARIF support under
**Settings → Tools → SARIF**.

---

## Webhook → Slack example

```python
# slack_webhook.py
from flask import Flask, request
import json, os, requests

app = Flask(__name__)
SLACK_URL = os.environ["SLACK_WEBHOOK_URL"]

@app.post("/mri-to-slack")
def receive():
    data = request.json
    score = data.get("score", {}).get("overall", "?")
    band = data.get("score", {}).get("band", "?")
    color = {"excellent": "good", "good": "good", "fair": "warning", "poor": "warning", "critical": "danger"}.get(band, "warning")
    emoji = {"excellent": "🟢", "good": "🟢", "fair": "🟡", "poor": "🟠", "critical": "🔴"}.get(band, "⚪")
    
    requests.post(SLACK_URL, json={
        "attachments": [{
            "color": color,
            "title": f"{emoji} {data['project_name']} — score {score} ({band})",
            "text": f"Scan {data['scan_uuid'][:8]} finished in {data.get('duration_s', 0):.2f}s",
            "fields": [
                {"title": "Critical", "value": data.get("findings_count", {}).get("critical", 0), "short": True},
                {"title": "High", "value": data.get("findings_count", {}).get("high", 0), "short": True},
                {"title": "Medium", "value": data.get("findings_count", {}).get("medium", 0), "short": True},
                {"title": "Low", "value": data.get("findings_count", {}).get("low", 0), "short": True},
            ]
        }]
    })
    return "ok"
```

Run this on your server, point project-mri's webhook URL at it, and you have
real-time Slack notifications.

---

## Reverse proxy + public access

If you want to expose the dashboard publicly (e.g., for a team):

### nginx + HTTPS

```nginx
server {
    listen 443 ssl;
    server_name mri.yourcompany.com;
    ssl_certificate /etc/letsencrypt/live/mri.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mri.yourcompany.com/privkey.pem;

    # Security headers (mirror project-mri's defaults)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://127.0.0.1:7331;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Caddy

```caddy
mri.yourcompany.com {
    reverse_proxy 127.0.0.1:7331 {
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

### Binding

By default `mri serve` listens on `127.0.0.1` (loopback only). To bind on all interfaces:

```bash
MRI_HOST=0.0.0.0 mri serve
```

> ⚠️ Binding to `0.0.0.0` without a reverse proxy exposes the dashboard to the entire
> network. **Don't do this** unless you have additional auth (VPN, basic auth at the
> proxy, etc.).

### Adding basic auth at the proxy

```nginx
auth_basic "project-mri";
auth_basic_user_file /etc/nginx/.htpasswd;
```

Or use OAuth2-proxy, Cloudflare Access, etc., in front.

---

## What's *not* integrated (yet)

- **Email notifications** — PRs welcome
- **GitHub Checks API** — coming in v0.4
- **GitLab Commit Status API** — coming in v0.4
- **Jira / Linear ticket creation** — use the webhook + your own automation

If you need something specific, the [HTTP API](./API.md) gives you full programmatic
access — anything the CLI or dashboard can do, you can do.