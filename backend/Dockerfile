# syntax=docker/dockerfile:1.7
# ---------- Stage 1: builder ----------
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

# Install dependencies first (better layer caching)
COPY requirements.txt ./
# Pin tree-sitter<0.21 (the bundled tree_sitter_languages is broken on 0.21+)
RUN sed -i 's/tree-sitter.*/tree-sitter<0.21/' requirements.txt || true
RUN pip install --prefix=/install -r requirements.txt

# Copy source
COPY mri ./mri
COPY pyproject.toml README.md ./

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