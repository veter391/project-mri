# Contributing to Project MRI

Thank you for your interest in contributing! Project MRI is an open-source codebase
intelligence tool, and we welcome contributions of all sizes.

## Code of Conduct

This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md). By
participating, you agree to uphold it. Report violations to conduct@project-mri.dev.

## How can I contribute?

- **Bug reports** — open an issue with reproduction steps
- **Feature requests** — open an issue describing the use case
- **Documentation** — typo fixes, clarifications, examples
- **Code** — bug fixes, new analyzers, performance improvements

## Development setup

### Prerequisites

- Python 3.10+ (3.11 recommended)
- Node.js 20+
- Git

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .[dev]
```

### Frontend

```bash
npm install
```

## Pull request workflow

1. **Fork & branch**: `git checkout -b feat/my-feature`
2. **Test**: `pytest` (backend) + `npm run build` (frontend)
3. **Lint**: `ruff check` + `bandit -r mri/`
4. **Commit**: Use [Conventional Commits](https://www.conventionalcommits.org/) format
   - `feat: ...` new feature
   - `fix: ...` bug fix
   - `docs: ...` documentation only
   - `refactor: ...` code change that neither fixes a bug nor adds a feature
   - `test: ...` add or fix tests
   - `chore: ...` tooling, deps, etc.
5. **Push** and **open a PR** with a clear description

CI runs automatically on every PR:
- Lint (ruff, bandit, mypy)
- Tests on Python 3.10, 3.11, 3.12
- Docker build
- Security audit

## Adding a new analyzer

Analyzers are async classes in `backend/mri/analyzers/`. The base class is `BaseAnalyzer`.

```python
from mri.analyzers.base import BaseAnalyzer

class MyAnalyzer(BaseAnalyzer):
    name = "my_analyzer"
    score_label = "my_score"
    weight = 1.0

    async def analyze(self, ctx):
        self._start()
        try:
            # ... compute findings ...
            self._add_finding(
                severity="medium",
                category="my_category",
                title="Example finding",
                description="...",
                target_path="src/foo.py",
                score=75.0,
            )
            # ... compute score ...
            self._set_score(75.0, ["contributor explanation"])
            self._finish_ok()
        except Exception as exc:
            self._finish_err(str(exc))
```

Then register it in `backend/mri/services/scanner.py`:

```python
class Scanner:
    ANALYZERS: list[type[BaseAnalyzer]] = [
        GitHistoryAnalyzer,
        ArchitectureAnalyzer,
        # ...
        MyAnalyzer,  # ← add here
    ]
```

## Coding conventions

### Python

- Type hints everywhere (mypy checked)
- Black formatting (line length 100)
- Pydantic v2 for all data models
- Async-first; `asyncio.to_thread` for blocking calls
- Structured logging via `mri.logging_setup.get_logger`
- Constants in UPPER_SNAKE_CASE
- No `print()` — use logger

### TypeScript

- Strict mode enabled
- ES modules, `.js` extension in imports
- No `any` (use `unknown` if needed)
- DOM access goes through helpers, not raw queries

## Reporting security issues

See [SECURITY.md](./SECURITY.md) — please do **not** open public issues for
security vulnerabilities. Email security@project-mri.dev instead.