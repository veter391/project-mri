# syntax=docker/dockerfile:1.7
# ---------- Stage 1: dashboard (Node) ----------
# The dashboard is built inside the image with the same `pnpm build` used
# locally, so the image never depends on a developer having built it first.
# node >= 22.13 is required by pnpm 11 (see root package.json "engines")
FROM node:22-slim AS frontend

ENV CI=1
RUN corepack enable
WORKDIR /build

# Workspace manifests first for layer caching; the lockfile must see every
# workspace package or --frozen-lockfile fails.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
# Source must land before `pnpm install`: copying it afterwards would overlay
# the workspace dir and wipe the node_modules links pnpm just created.
COPY apps/dashboard apps/dashboard
RUN pnpm install --frozen-lockfile --filter @mri/dashboard...

# `build` = next build (static export) + embed into src/mri/_frontend/dashboard
RUN pnpm --filter @mri/dashboard build

# ---------- Stage 2: builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for tree-sitter
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install dependencies first (better layer caching). requirements.txt is
# generated from uv.lock and fully hash-pinned, so pip verifies every artifact.
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# Copy source (src-layout)
COPY src ./src
COPY pyproject.toml README.md ./

# Take the dashboard from the Node stage, never from the build context
COPY --from=frontend /build/src/mri/_frontend ./src/mri/_frontend

# Install the package itself
RUN pip install --prefix=/install --no-deps .

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MRI_DB=/data/mri.db \
    MRI_LOG_FORMAT=json \
    MRI_LOG_LEVEL=INFO

# Non-root user
RUN groupadd -r mri && useradd -r -g mri -d /app -s /sbin/nologin mri \
    && mkdir -p /app /data \
    && chown -R mri:mri /app /data

# Runtime deps (no gcc needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

USER mri

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:7331/api/health').status == 200 else 1)" \
    || exit 1

EXPOSE 7331

# tini handles signal forwarding for graceful shutdown
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default: run the API server + dashboard through the guarded CLI entrypoint.
# `mri serve` fail-closes on a public bind without auth (set MRI_API_KEYS, or
# MRI_ALLOW_INSECURE=1 on a trusted network). Proxy-header trust is intentionally
# NOT enabled by default; configure it explicitly when behind a known proxy.
CMD ["mri", "serve", "--host", "0.0.0.0", "--port", "7331"]

# Labels
LABEL org.opencontainers.image.title="project-mri" \
      org.opencontainers.image.description="MRI scan for your codebase" \
      org.opencontainers.image.source="https://github.com/project-mri/project-mri" \
      org.opencontainers.image.licenses="MIT"