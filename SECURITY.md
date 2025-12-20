# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Email security@project-mri.dev with:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (optional)

We will acknowledge receipt within **48 hours** and aim to provide a fix
or mitigation within **7 days** for critical issues, **30 days** for others.

## Security Features

Project MRI takes security seriously:

- **Single-user admin model** — bcrypt(12) hashed password, no registration
- **JWT HS256 tokens** (24h TTL, auto-generated secret stored in DB)
- **Path allowlist**: Restrict scannable paths via `MRI_ALLOWED_ROOTS` env var
- **API key auth**: Optional bearer-token auth via `MRI_API_KEYS` env var
- **Per-scan URL validation**: Reject unknown git hosts; PAT injection for known ones
- **Rate limiting**: Per-IP token bucket (60/min default, 5/min for scans)
- **Body size cap**: Default 1 MiB (`MRI_MAX_REQUEST_BYTES`)
- **CORS lockdown**: Origins must be explicitly listed (`MRI_CORS_ORIGINS`)
- **Security headers**: CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy
- **No eval / shell injection**: All paths and inputs are validated
- **Tarfile path-traversal protection**: `mri restore` rejects `..`/symlinks/special files
- **HMAC-SHA256 webhook signing**: `X-MRI-Signature` header on outgoing webhooks
- **No telemetry**: Nothing leaves your machine
- **Constant-time API key comparison**: Prevents timing attacks
- **JWT vs API key disambiguation**: server checks `token.count(".") == 2` to tell them apart

## Deployment Recommendations

### Production checklist

- [ ] Set `MRI_API_KEYS` to a strong random value (32+ bytes, URL-safe)
- [ ] Set `MRI_ALLOWED_ROOTS` to ONLY the directories you want scannable
- [ ] Run behind a reverse proxy (nginx, Caddy) that terminates TLS
- [ ] Set `MRI_CORS_ORIGINS` to your specific domain (no wildcards)
- [ ] Mount the database on a persistent volume
- [ ] Set up log aggregation (the JSON logs are structured for this)
- [ ] Scrape `/metrics` into Prometheus / VictoriaMetrics
- [ ] Use `/api/health/deep` for Kubernetes readiness probes
- [ ] Run as non-root (Dockerfile does this)
- [ ] Drop unnecessary Linux capabilities
- [ ] Mount repo directories as **read-only** in Docker
- [ ] Don't expose port 7331 directly to the internet — always proxy

### Example nginx config

```nginx
server {
    listen 443 ssl http2;
    server_name mri.example.com;

    ssl_certificate /etc/ssl/certs/mri.crt;
    ssl_certificate_key /etc/ssl/private/mri.key;

    # Pass through client cert/IP for rate-limit accounting
    set $client_ip $remote_addr;

    location / {
        proxy_pass http://127.0.0.1:7331;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $client_ip;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Don't let the proxy buffer too long — keep latency low
        proxy_buffering off;
        proxy_read_timeout 600s;  # long scans
    }
}
```

## Threat Model

### In scope

- API key brute-force / leak
- Path traversal to scan protected directories
- Denial-of-service via large requests or many scans
- Header injection (e.g., via user-controlled paths in logs)
- WebSocket abuse (slow consumers blocking the bus)
- SQL injection via dynamic queries

### Out of scope (current design)

- Server-side code execution (no `eval`/`exec` on user data)
- Privilege escalation within the host (we don't read sensitive system files)
- Side-channel timing attacks beyond constant-time API key compare
- Memory corruption (Python is memory-safe)

## Security Audits

- Static analysis: `bandit -r mri/`
- Dependency scan: `safety check` / `pip-audit`
- Tests: `pytest tests/test_security.py` (39 tests)

Run all three before deployment:

```bash
cd backend
bandit -r mri/ -ll
safety check --file requirements.txt
PYTHONPATH=. pytest tests/test_security.py -v
```

## Disclosure Timeline

We follow **coordinated disclosure**:

1. Reporter emails security@project-mri.dev
2. We acknowledge within 48h
3. We work on a fix (typically 7–30 days depending on severity)
4. We release the fix and credit the reporter (if they wish)
5. After 90 days, or once a fix is widely deployed, full disclosure is published

## Hall of Fame

(No reported vulnerabilities yet — be the first!)