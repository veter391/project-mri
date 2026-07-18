# ADR-004 — Professional repo structure, Git workflow, and interface stack

> Status: **accepted**. Dual-model research (Opus 4.8 = structure, Sonnet 5 = workflow+stack),
> verified by me as final reviewer against real repos and live docs. Raw: workflow `wk7nk7v51`.
> Reference precedents (real, cited): Datasette, Grafana, Ruff, uv, PyPA packaging guide,
> release-please, FastAPI, Astro, trunkbaseddevelopment.com.

## Verification (I re-checked, did not trust on faith)

- **FastAPI `app.frontend("/", directory=..., fallback="index.html")` — VERIFIED to exist**
  (fetched https://fastapi.tiangolo.com/tutorial/frontend/; it is the current official pattern for
  serving a prebuilt static SPA/site — Astro/Vite/Svelte/etc.). This is post my knowledge cutoff, so
  I confirmed it live before building on it.
- **Datasette** genuinely ships its web UI as static assets inside the pip package, npm dev-only —
  the exact "no Node at runtime" precedent for us. **Grafana** bakes a compiled SPA into its backend
  artifact (Go embed) — same shape, different language.
- **release-please** (Google) is real, multi-language, Python-capable, PR-based, produces
  Keep-a-Changelog + GitHub Releases. Correctly preferred over semantic-release (npm-centric).

## Decision 1 — Monorepo layout (sparse root)

```
project-mri/
├─ README.md LICENSE CHANGELOG.md CITATION.cff SECURITY.md
├─ CODE_OF_CONDUCT.md CONTRIBUTING.md pyproject.toml Dockerfile
├─ .gitignore .gitattributes .editorconfig .dockerignore .github/
├─ src/mri/                # Python src-layout. IMPORT NAME stays `mri`; dist name `project-mri`.
│  ├─ cli.py api/ analyzers/ db/ services/ models/ security.py …
│  └─ static/              # BUILT dashboard assets shipped in the wheel (no Node at runtime)
├─ tests/                  # pytest, mirrors src/mri/
├─ apps/dashboard/         # dashboard SOURCE → build emits into ../../src/mri/static/
├─ web/                    # public DEMO/marketing site (its own deployable; src/ styles/ public/ dist/)
├─ docs/                   # all loose root .md consolidated (install, config, api, dashboard, integrations)
├─ examples/sample-report/ # mri-report.html as a checked-in reference artifact
└─ deploy/                 # install.sh, docker-compose.yml
```

**Deviation from the research (deliberate, lower-risk):** keep the Python **import name `mri`**
(move `backend/mri/` → `src/mri/`), do NOT rename to `project_mri`. Renaming the import would churn
every `from mri.…` across the code + tests + entry point for no real gain; distribution name stays
`project-mri` (dist name ≠ import name is normal). Root keeps only README/LICENSE/CHANGELOG/CITATION/
SECURITY/COC/CONTRIBUTING/pyproject/Dockerfile/dotfiles/.github (all GitHub-recognized-at-root).

## Decision 2 — Git workflow

- **Trunk-based** (`main` always green & releasable), NOT git-flow (no second release line to justify it).
- Non-trivial change → short-lived `feat/…`,`fix/…`,`refactor/…` branch → PR → **squash-merge** →
  **linear history**. Trivial (typo/version) may go direct to `main`, still gated by required checks.
- **GitHub Rulesets** on `main` (current mechanism, not legacy branch-protection UI): require status
  checks (lint · typecheck · tests · build), require linear history, require signed commits, block
  force-push + deletion, and **do-not-allow-bypass (owner not exempt)**.
- **Conventional Commits**, enforced by a CI commit-lint gate (also the input release-please parses).
- **release-please** (manifest mode) → standing "release PR" that bumps `pyproject.toml` + CITATION
  version, writes `CHANGELOG.md`, and on merge tags + creates a GitHub Release; PyPI publish via
  **trusted publishing (OIDC)**, never a long-lived token.

## Decision 3 — Interface stack

- **Both** the self-hosted **dashboard** and the public **demo/marketing site** → **Astro with
  `output: 'static'`** (flat `dist/`, hashed assets, no server entrypoint), one shared design-token/CSS
  layer. Interactive dashboard widgets (live filter/charts) as thin islands only where needed.
- **Dashboard** `dist/` is vendored into `src/mri/static/` and served by FastAPI
  **`app.frontend("/", directory=static, fallback="index.html")`** → `pip install project-mri` + `mri
  serve`, **zero Node at runtime** (the hard constraint). **Demo site** builds separately in CI and
  deploys to Pages/Cloudflare — never touches the Python package.
- **Rejected:** Next.js (assumes a Node runtime; RSC/SSR is dead weight here) · keep vanilla-TS+tsc
  (tsc is not a bundler — no code-splitting/hashing/dev-server, two diverging toolchains = the current
  "sprawl") · SvelteKit-server (adapter/server default reintroduces Node) · Dash/Streamlit (need a live
  Python UI process, not static files; wrong for a public SEO site).

## Execution sequence (phased, no big-bang — each phase its own branch + green CI)

- **R1 — Structure/hygiene:** move site→`web/`, `dashboard/`→`apps/dashboard/`, docs→`docs/`,
  `mri-report.html`→`examples/`, `backend/mri/`→`src/mri/` (+ pyproject/CI/Dockerfile paths, tests
  green), promote a proper root README, clean root. High visibility, no framework change yet.
- **R2 — Workflow/CI:** GitHub Ruleset on `main`, expand CI (lint/typecheck/tests/build + `mri` CLI
  self-scan smoke), commit-lint, release-please + PyPI trusted publishing, Dependabot as a visible check.
- **R3 — Interface rebuild (Astro):** migrate the demo/marketing site to Astro first, then the
  dashboard; wire `app.frontend()`; elevate the terminal-aesthetic design a level up in the shared
  token layer. This is the "interface on the highest level" the owner asked for.

The in-flight `fix/frontend-accessibility` PR (vanilla-TS a11y fixes) stays valid for the interim and
informs the Astro dashboard; merge it before R1 so R1 reorganizes the corrected files.

---

## SUPERSEDING RECONCILIATION (2026-07-11) — framework = Next.js, verified

Owner requires a recognizable, principal-grade monorepo with **Next.js** as the visibly-leading
framework (consistent with the owner's other repos). This supersedes the Astro choice above.

**Final structure** (reconciled from dual-model research + verified precedents Prefect/Gradio/MLflow):

```
project-mri/
├─ pyproject.toml            # Python pkg (src-layout, hatchling) at ROOT
├─ package.json  pnpm-workspace.yaml   # JS workspace (delete package-lock.json → pnpm-lock.yaml)
├─ apps/
│  ├─ web/                   # Next.js App Router — public demo/marketing site (normal build; Vercel/CF)
│  └─ dashboard/             # Next.js output:'export' — self-hosted UI, builds into the Python package
├─ src/mri/                  # Python package (CLI+API+analyzers); import name stays `mri`
│  └─ _frontend/dashboard/   # gitignored; apps/dashboard `out/` copied here at build; force-included in wheel
├─ tests/  docs/  examples/  scripts/  .github/  deploy/
└─ README LICENSE CHANGELOG CITATION SECURITY COC CONTRIBUTING SUPPORT
```
(Chose `src/mri` at root + `apps/` over the wrapper-`backend/` variant: pyproject-at-root + src-layout is
the modern Python-package norm — Ruff/uv/PyPA — and `apps/` makes Next the visible lead. Prefect is the
closest live precedent: `src/prefect/` + frontend source at root, frontend built into `src/prefect/server/ui`
via a hatch build hook + `artifacts`, gitignored-but-shipped-in-wheel. We mirror it.)

**Dashboard embed + serve (verified):** `apps/dashboard` (Next `output:'export'`, `images.unoptimized`,
all data client-fetched from FastAPI) → `next build` → `out/` → copied into `src/mri/_frontend/dashboard/`
(gitignored) → force-included in the wheel via hatchling `[tool.hatch.build.targets.wheel.artifacts]` →
served by **`app.frontend("/", directory=<importlib.resources path>, fallback="index.html")`** with FastAPI
pinned `>=0.139`; documented Plan-B = `StaticFiles(html=True)` + 404→index.html catch-all. **Fix the real
wheel-path bug**: locate the dir via `importlib.resources.files("mri")/"_frontend/dashboard"`, not `Path(__file__)`.

**Workflow** unchanged from Decision 2 (trunk-based, rulesets, Conventional Commits, release-please).

**Honest scope:** this is a large migration — it includes REBUILDING the marketing site and the dashboard as
Next.js apps (real frontend work, multi-step), not just moving files. Execute methodically in a branch, permanent
core first, each step green — never a big-bang. Sequence:
- **S1 — Python src-layout + monorepo skeleton** (move `backend/mri`→`src/mri`, pyproject→root+hatchling,
  fix the wheel-path serving via importlib.resources, delete package-lock, add pnpm-workspace, CI/Dockerfile,
  `python -m build && pip install dist/*.whl && mri serve` smoke test green). Permanent; not thrown away later.
- **S2 — apps/web** (Next demo site rebuilt from the current *.html/css/ts; add redirects/sitemap for SEO).
- **S3 — apps/dashboard** (Next output:export rebuilt from dashboard/; wire the embed + `app.frontend`).
- **S4 — remove old root sprawl** once S2/S3 replace it; senior README describing the architecture.


---

## Amendment — 2026-07-18 (implementation deviations)

Recorded when the deviations were found during Audit gate 0. Both are accepted;
they change how the decision was implemented, not the decision itself.

### 1. Build backend: setuptools `package-data`, not hatchling `artifacts`

The record specified hatchling with `[tool.hatch.build.targets.wheel.artifacts]`
plus a build hook to sequence the frontend build. The implementation stayed on
setuptools and force-includes the gitignored export with a recursive
`package-data` glob (`_frontend/**/*`).

**Consequence, accepted with a mitigation:** `package-data` force-includes but
does not *sequence*. On a clean checkout `src/mri/_frontend/` does not exist, so
`python -m build` would happily emit a dashboard-less wheel that installs fine
and 404s at runtime. Since the sequencing guarantee is what hatchling was chosen
for, it is replaced by an explicit gate: the `package` job in `ci.yml` builds the
wheel, asserts `mri/_frontend/dashboard/index.html` and the CSP manifest are
inside it, installs it into a clean virtualenv, and requires `/dashboard/` to
answer 200. A release that skipped the frontend build cannot pass CI.

Revisit hatchling if the guard proves insufficient; the ADR's reasoning stands.

### 2. Dashboard serving: `StaticFiles` subclass, not `app.frontend()`

`app.frontend()` exists in current FastAPI, but using it would pin a floor of
FastAPI 0.139 on every self-hosting user. The implementation mounts a
`StaticFiles(html=True)` subclass located through `importlib.resources`, which
works across the supported FastAPI range and keeps the dependency at `>=0.110`.

Deliberate trade: slightly more code here, far fewer version constraints on a
tool people install into their own environments.

### 3. Content-Security-Policy for the embedded export

Not anticipated by the record. The Next App Router bootstraps through inline
`<script>` tags, which the API's `script-src 'self'` blocks outright — the
dashboard rendered blank in every browser. The build now hashes each inline
script (`apps/dashboard/scripts/embed.mjs` → `csp-script-hashes.json`) and the
server allows exactly those hashes, scoped to `/dashboard`. `'unsafe-inline'` is
never used, and the API keeps the strict policy.
