# Packaging & Distribution

How project-mri is packaged and how to install it. The Python package is the
product; the dashboard ships inside it as a pre-built static bundle, so an
operator needs Python only — no Node runtime at install time.

---

## What ships in the wheel

`project_mri-<version>-py3-none-any.whl` bundles:

- the `mri` package (engine, analyzers, fusion layers, API, CLI);
- the SQL migrations (`mri/db/**/*.sql`);
- the report templates;
- the **pre-built dashboard** static export under `mri/_frontend/dashboard/`
  (built with `pnpm --filter @mri/dashboard build`, embedded at package-build
  time), so `mri serve` serves it with no Node runtime.

Entry points: `mri` and `mri-server` (both → `mri.cli:cli`).

> **Build note:** build the dashboard with `NODE_ENV=production`. A dev
> `NODE_ENV` makes Next's static export fail at prerender with an `<Html>` import
> error — an environment gotcha, not a code defect.

---

## Install

### pip (verified working from a clean environment)

```
pip install project-mri
mri init            # create the admin user + config
mri serve           # dashboard at http://localhost:7331/dashboard/
mri scan /path/to/repo
```

Verified: the built wheel installs into a fresh virtualenv and `mri --version`,
`import mri`, and `mri --help` all work from the installed path.

### pipx (isolated CLI)

```
pipx install project-mri
```

### Container

A `Dockerfile` and `deploy/docker-compose.yml` are provided. The container binds
fail-closed: a non-loopback bind without auth is refused
([ADR-013](adr/ADR-013-auth-posture-fail-closed-local-first.md)), so a bare
`docker run` on `0.0.0.0` without a configured user or `MRI_ALLOW_INSECURE=1`
exits rather than serving unauthenticated.

---

## Reproducible dependencies

- `uv.lock` pins the full graph; `requirements.txt` is generated from it with
  hashes (`uv export --no-dev --no-emit-project`). The optional `mcp` extra
  (`pip install project-mri[mcp]`) is pinned in `uv.lock` but kept out of the
  core `requirements.txt` so the default install stays lean.
- `pip-audit` reports no known vulnerabilities against the pinned set (see
  [AUDIT.md](AUDIT.md)).

---

## Publishing — owner-gated

Actual publication is deliberately **not** automated here; it needs the owner's
decision and credentials:

- **PyPI:** publish `project_mri` to TestPyPI, verify a clean `pip install` from
  it, then release to PyPI. (License is MIT; there is no paid gating.)
- **Container registry:** push the built image once a registry/namespace is
  chosen.
- **Version / tag / CHANGELOG:** cut the tag and update `CHANGELOG.md` at release.

Until the owner confirms the target registry/domain, the artifacts are
release-ready but unpublished.
