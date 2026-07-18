# Installing project-mri

**project-mri** is a self-hosted codebase intelligence tool. Install it once, run it on
your own machine or server, and use the local dashboard. No SaaS, no telemetry, no
account registration. Just `pip install project-mri` and you're done.

---

## Quick install (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/veter391/project-mri/main/scripts/install.sh | bash
```

This will:
1. Detect Python 3.10+ on your system
2. `pip install project-mri` (and all its dependencies)
3. Print next-step instructions

To install for the current user only (no sudo):
```bash
curl -fsSL https://raw.githubusercontent.com/veter391/project-mri/main/scripts/install.sh | bash -s -- --user
```

To install system-wide (with sudo):
```bash
curl -fsSL https://raw.githubusercontent.com/veter391/project-mri/main/scripts/install.sh | bash -s -- --system
```

---

## Install with pip directly

If you already have Python 3.10+ and prefer not to use the shell installer:

```bash
python3 -m pip install --user project-mri
```

Then add `~/.local/bin` to your PATH if it's not already:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## Install with Docker

No image is published yet — build it from source. The image builds the dashboard
itself (Node stage), so it never depends on your working tree:

```bash
git clone https://github.com/veter391/project-mri.git
cd project-mri
docker build -t project-mri .
docker run -d \
  --name project-mri \
  -p 7331:7331 \
  -v mri-data:/home/mri/.cache/project-mri \
  project-mri
```

Dashboard will be at `http://localhost:7331/dashboard/`.

---

## Install from source (development)

Requires Python 3.10+ and, for the web apps, Node >= 22.13 (pnpm 11 needs it).

```bash
git clone https://github.com/veter391/project-mri.git
cd project-mri
```

**Python — reproducible (recommended).** `uv` is a dev-time-only tool; it is not
a runtime dependency of project-mri. `uv.lock` pins the entire dependency graph
exactly, so every contributor and CI run resolves identically:

```bash
pip install uv          # or: pipx install uv
uv sync --extra dev     # creates .venv from uv.lock, exactly
uv run mri init
uv run mri serve
```

**Python — pip fallback.** No uv required. `requirements.txt` is generated from
`uv.lock` and is fully hash-pinned, so pip verifies every artifact:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # exact, hash-verified runtime deps
pip install -e ".[dev]"            # the package itself + dev tools
mri init
mri serve
```

> Dependency policy: the root `pyproject.toml` declares compatible **ranges** so
> the published wheel does not over-constrain consumers. Exact reproducibility
> comes from `uv.lock` (and the `requirements.txt` derived from it). Never edit
> `requirements.txt` by hand — regenerate it:
> `uv export --format requirements-txt --no-dev --no-emit-project -o requirements.txt`

**Web apps (site + dashboard):**

```bash
pnpm install
pnpm dev:web           # marketing site
pnpm dev:dashboard     # dashboard
pnpm build:dashboard   # static export embedded into src/mri/_frontend
```

---

## First-run setup

After installation, create your admin user:

```bash
mri init
```

You'll be prompted for:
- **Username** (default: `admin`)
- **Password** (8+ characters, required)
- **Config path** (default: `~/.config/project-mri/.mri.yml`)

`mri init` is idempotent — if you've already initialized, it tells you how to
reset or change credentials.

---

## Start the server

```bash
mri serve
```

Default: listens on `127.0.0.1:7331` (local-only). Open `http://localhost:7331/dashboard/`
in your browser.

To bind to all interfaces (e.g., to expose via reverse proxy):
```bash
MRI_HOST=0.0.0.0 mri serve
```

---

## Quick start: scan your first repo

```bash
# One-shot scan of a local directory
mri scan /path/to/your/code

# Scan a git URL (shallow clone, auto-cleanup)
mri scan https://github.com/yourorg/yourrepo.git

# Watch a directory and re-scan on every change
mri watch /path/to/your/code

# See recent scans
mri list

# Run a synthetic demo (no real repo needed)
mri demo
```

Reports are written to `~/.cache/project-mri/reports/<uuid>.html`.

---

## Backup & restore

```bash
# Backup DB + config to a tar.gz
mri backup ./mri-backup.tar.gz

# Restore later
mri restore ./mri-backup.tar.gz
```

---

## Update

```bash
# If installed with pip:
pip install --upgrade project-mri

# Or use the CLI:
mri upgrade

# Or with docker:
docker pull ghcr.io/project-mri/project-mri:latest
```

---

## Uninstall

```bash
pip uninstall project-mri
# Optionally wipe all data:
rm -rf ~/.cache/project-mri
rm -rf ~/.config/project-mri
```

---

## Troubleshooting

**"mri: command not found"** — `~/.local/bin` isn't in your PATH. Run:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
Add this line to your `~/.bashrc` / `~/.zshrc` to make it permanent.

**"Permission denied" on `pip install`** — either pass `--user` to the installer, or use a virtualenv:
```bash
python3 -m venv ~/mri-venv
source ~/mri-venv/bin/activate
pip install project-mri
```

**Port 7331 already in use** — choose another port:
```bash
MRI_PORT=8080 mri serve
```

**"git not found"** — `git` is needed only for repository cloning and `mri scan <url>`.
Install with your OS package manager (`apt install git`, `brew install git`, etc.).

**Forgot admin password** — reset and start over:
```bash
mri reset
mri init
```

**Database locked** — only one `mri serve` instance can use the DB at a time. Kill any
orphaned processes:
```bash
pkill -f 'mri serve'
```

---

## Next steps

- See [DASHBOARD.md](./DASHBOARD.md) for dashboard usage
- See [INTEGRATIONS.md](./INTEGRATIONS.md) for GitHub/GitLab PAT, webhooks, CI/CD
- See [CONFIG.md](./CONFIG.md) for the full `.mri.yml` reference
- See [API.md](./API.md) for HTTP API documentation