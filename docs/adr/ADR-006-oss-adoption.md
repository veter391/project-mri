# ADR-006 — Which libraries we adopt, and which we do not

**Status:** Accepted · 2026-07-19

## Context

The rebuild plan lists seven libraries to adopt "instead of reinventing":
PyDriller, tree-sitter-language-pack, lizard, grimp/import-linter, NetworkX,
argon2-cffi, and limits. Reuse over reinvention is the right instinct, but it is
an instinct, not a verdict. A library earns its place by doing something we do
not do, or doing it better — not by appearing on a list.

Every item below was measured or researched before deciding. This is a
local-first tool that users install on their own machines, so each dependency is
something they carry, and one dead dependency has already bitten this project.

## Decisions

### Adopted: tree-sitter-language-pack

`tree-sitter-languages` was unmaintained with no wheels for CPython 3.13+, which
broke parsing on modern Python. Replaced. (Covered in the migration commit.)

### Adopted: lizard

Adds cyclomatic complexity, which nothing computed — while the README had been
advertising it as a feature. Pure Python, 27 languages, accepts source text so
it reads from the shared cache rather than reopening files.

It also paid for itself immediately: the first run reported a function at
complexity 112, which turned out to be a minified bundle. `EXCLUDE_DIRS` covered
`.next` but not `_next`, the directory a Next.js *static export* writes to, so
40 build artifacts were being analysed as source and skewing every metric. With
that fixed, the complexity analyzer runs **faster than before lizard existed**
(566 ms → 409 ms), because it stopped wasting time on minified chunks.

### Declined: NetworkX

Proposed for cycle detection. Our iterative Tarjan already returns correct SCCs
and, measured on a 5,000-node graph, is marginally faster: **7.7 ms against
NetworkX's 8.5 ms**, with identical results. Adopting it would add a dependency
to buy parity. The existing implementation is also already pinned by tests
against the recursion limits that motivated writing it.

Revisit if we need graph algorithms beyond SCC — centrality, flow, layout — at
which point NetworkX earns its place properly.

### Declined for now: argon2-cffi

The plan says "adopt argon2-cffi with sane params". OWASP does rank Argon2id
above bcrypt, and for a multi-user service that ranking should be followed. It
does not transfer here, and the reasoning matters more than the conclusion:

- Argon2's advantage is memory-hardness against **mass offline cracking of a
  stolen hash database**. This installation has exactly one hash, on the user's
  own disk, beside the database and the JWT signing key it protects. An attacker
  who can read it has already won by easier routes.
- It is not a replacement but an addition. Existing installs hold bcrypt hashes,
  so bcrypt stays as a dependency regardless and the verify path becomes
  permanently dual-algorithm.
- `memory_cost` is a real allocation held for the hash's duration. The
  argon2-cffi default is RFC 9106's 64 MiB at p=4 — not OWASP's numbers, which
  top out at 46 MiB with p=1. On a 512 MB container that turns a slow login into
  a possible OOM kill: a worse failure mode than a slow one, and it lands on the
  user's machine.
- bcrypt at cost 12 measures ~195 ms here, above OWASP's minimum work factor of
  10. pyca/bcrypt is actively maintained.

**If this is revisited** — a multi-user mode, or a compliance requirement — the
route is: dispatch on the `$2b$` / `$argon2id$` prefix, verify with the matching
library, rehash inside the successful-login branch, and choose OWASP's
`m=19456, t=2, p=1` explicitly rather than accepting the library default. Do
**not** reach for passlib: it has not shipped since 2020 and depends on the
`crypt` module that Python 3.13 removed, which is precisely the dead-dependency
trap this project already fell into once. `pwdlib` is the maintained option.

The honest framing is that this item is conformance, not a security fix. The
JWT secret's storage and rotation, the 24-hour token lifetime, and the file
permissions on the database all guard the same asset and are likelier to be the
real weak link.

### Declined: PyDriller

Proposed for git mining. It wraps GitPython and materialises per-commit
modification objects, which means a `git diff` per commit — the exact pattern
this phase removed, where 36 ms per commit became six minutes on a
10,000-commit history.

Measured over 30 commits: **54.9 ms per commit against our 5.0 ms**, an 11x
regression. Adopting it would undo that work to gain a nicer object model.

Correctness is not the differentiator: on a single commit both produce
**identical** per-file added/deleted counts (4/4 of the shared files; the
apparent extras were only Windows path separators). A first pass suggested the
churn totals differed by 2x, but that was an error in my benchmark — PyDriller
traverses oldest-first while `git log -30` returns newest-first, so the two runs
covered different commits. The speed comparison stands; the correctness one
never showed a real difference.

If the fusion layers later need per-modification detail, more format specifiers
on the existing `git log` will produce it at a fraction of the cost.

### Declined: limits

Proposed to replace the hand-rolled rate limiter. The argument for it was
genuine and not about speed: my own implementation shipped with two real defects
(unbounded IP-key growth, no capacity ceiling), which is decent evidence that
hand-rolling a security-adjacent component is error-prone.

That argument collapsed on inspection. `limits` 5.8.0 works fine on Python 3.14
with three small pure-Python dependencies, but its `MemoryStorage` retains
**all 20,000 keys** in a 20,000-distinct-address test — the *same* unbounded
growth that was the bug worth fixing. It has an internal event expiry but no cap
on distinct keys, so adopting it would still require the capacity ceiling on
top, and the library would be buying only the moving-window arithmetic, which is
a per-key timestamp list filtered by age and readable in eight lines.

Its real value is storage backends — Redis, Memcached — for rate limiting shared
across processes. This tool is a single local process. Revisit if it ever runs
as a multi-instance service.

### Declined: grimp / import-linter — but the evaluation changed the code anyway

grimp is healthy (3.15, July 2026, wheels for 3.10-3.14) and it does not need
the analysed code to be importable, which was the objection I expected to
disqualify it: it parses statically and only uses `find_spec` to locate the
package directory. So the "we just cloned an untrusted repo with nothing
installed" problem largely dissolves.

It was declined on fit rather than quality:

- It is Python-only, while the import graph is shared across six languages. It
  yields a whole graph of dotted module names, not per-file import lists, so
  keeping one comparable graph needs a translation layer back to repo-relative
  paths.
- It fails all-or-nothing per package, so the existing extractor stays as a
  fallback regardless. That leaves three things to maintain — grimp, the
  heuristic, and the arbitration between them — and the same repository can then
  produce different metrics depending on which path fired. Non-determinism is
  worse in a reporting tool than a consistent, known limitation.
- It requires knowing the package roots and putting them on `sys.path`. For an
  arbitrary repository that is the layout-detection problem we would be adopting
  it to avoid, plus `sys.path` mutation pointing at freshly cloned untrusted
  code.

import-linter is a contract checker built *on* grimp, relevant only if the
product ever offers user-defined architecture rules. Not today.

**The evaluation was still worth it, because it identified the real defect.**
Relative imports were producing `/helpers.py` and `//core.py` — keys matching no
file — so every intra-package edge disappeared. Packages that use relative
imports internally, which is most well-factored ones, showed no cycles and near
zero internal coupling and read as maximally stable. The fix is a resolver over
the file list we already have: dots counted, path walked up, candidates checked
against real files, unresolved targets classified external instead of invented.
That closes four of the five known weaknesses with no dependency, no second code
path, and identical behaviour across languages. Source roots are derived from
where top-level packages actually sit, so src-layout resolves too.

Reconsider grimp if the product starts reporting Python-specific facts that need
true module semantics — import line numbers, `TYPE_CHECKING` classification,
external dependency inventories — or if user-defined contracts arrive.

## Consequences

Two of the seven listed libraries are adopted; five are declined. Each decision
carries the number or the argument that produced it — NetworkX on a benchmark,
PyDriller on a benchmark, `limits` on inspecting the exact defect it was meant
to prevent, argon2-cffi on the threat model, grimp on fit — so any of them can
be overturned by better evidence rather than by preference.

The plan's list is treated as candidates, not instructions. That is not a
licence to skip work: two of the evaluations changed the code anyway. lizard
exposed 40 build artifacts being analysed as source, and the grimp evaluation
found that relative imports were corrupting the dependency graph. Evaluating a
library honestly is worth doing even when the answer is no.
