"""Import extraction.

Two bugs lived here undetected because the AST path silently produced nothing
and the regex fallback quietly covered for it:

  * the walker only read quoted strings, which Python imports do not have, so
    the AST path found zero imports in every Python file;
  * node spans were sliced out of a `str` using byte offsets, which returns the
    wrong text as soon as a file contains a multi-byte character — an em dash in
    a comment is enough, and this codebase is full of them.
"""
from __future__ import annotations

from pathlib import Path

from mri.analyzers.base import ScanContext
from mri.analyzers.parsing import (
    extract_imports,
    get_parser_for,
    resolve_python_import,
    walk_imports,
)


def _ctx(tmp_path: Path) -> ScanContext:
    return ScanContext(project_path=tmp_path, branch="main", files=[], git=None)


def test_python_imports_are_found_via_the_ast():
    source = "import os\nimport a.b.c\nfrom pkg.mod import thing\n"
    tree = get_parser_for("python").parse(source.encode())
    found = walk_imports(tree.root_node, source)
    assert set(found) == {"os", "a.b.c", "pkg.mod"}


def test_javascript_imports_are_found_via_the_ast():
    source = 'import x from "./y";\nimport "./side";\n'
    tree = get_parser_for("javascript").parse(source.encode())
    assert set(walk_imports(tree.root_node, source)) == {"./y", "./side"}


def test_multibyte_characters_do_not_shift_the_extracted_text(tmp_path: Path):
    """Byte offsets against a str returned the wrong span. An em dash before the
    import was enough to turn `pathlib` into `thlib i`."""
    source = (
        "# a comment with an em dash — and another —\n"
        "from pkg.mod import x\n"
        "from neighbour import y\n"
    )
    # The targets must exist: resolution correctly drops anything that is not a
    # file here, so without them the test would pass while exercising nothing.
    ctx = _package(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/mod.py": "",
        "neighbour.py": "",
        "multibyte.py": source,
    })
    found = extract_imports(ctx, "multibyte.py", source)
    # Exact equality: a shifted span produced entries like "thlib i.py", which a
    # substring check would not reliably catch.
    assert set(found) == {"pkg/mod.py", "neighbour.py"}


def test_ast_and_regex_paths_agree_on_shape(tmp_path: Path):
    """Downstream keys the dependency graph on these strings, so both paths must
    produce the same form or the two would build different graphs."""
    source = "import os\nfrom pkg.mod import thing\n"
    ctx = _package(tmp_path, {"pkg/__init__.py": "", "pkg/mod.py": "", "plain.py": source})

    from mri.analyzers.parsing import _PY_IMPORT, resolve_python_import

    from_ast = extract_imports(ctx, "plain.py", source)
    from_regex = [
        resolved
        for m in _PY_IMPORT.finditer(source)
        if (resolved := resolve_python_import(ctx, "plain.py", m.group(1) or m.group(2)))
    ]
    # `os` is stdlib: it resolves to nothing on both paths, which is the point.
    assert set(from_ast) == set(from_regex) == {"pkg/mod.py"}


def test_relative_marker_is_not_emitted_as_a_module(tmp_path: Path):
    source = "from . import sibling\n"
    rel = "rel.py"
    (tmp_path / rel).write_text(source, encoding="utf-8")
    assert extract_imports(_ctx(tmp_path), rel, source) == []


# ---------------------------------------------------------------------------
# Import resolution against the files that actually exist
# ---------------------------------------------------------------------------


def _package(tmp_path: Path, layout: dict[str, str]) -> ScanContext:
    for rel, body in layout.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    from mri.services.scanner import Scanner

    return ScanContext(
        project_path=tmp_path, branch="main", files=Scanner._walk_files(tmp_path), git=None
    )


def test_relative_imports_resolve_to_real_files(tmp_path: Path):
    """`from .helpers import h` became the literal key "/helpers.py" and
    `from ..core import Thing` became "//core.py" — nodes matching no file. Every
    intra-package edge vanished, so packages using relative imports internally
    showed no cycles and read as maximally stable."""
    ctx = _package(tmp_path, {
        "pkg/__init__.py": "from .core import Thing\n",
        "pkg/core.py": "from .helpers import helper\n",
        "pkg/helpers.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/deep.py": "from ..core import Thing\nfrom .sibling import x\n",
        "pkg/sub/sibling.py": "",
    })
    assert extract_imports(ctx, "pkg/__init__.py", ctx.read_text("pkg/__init__.py")) == ["pkg/core.py"]
    assert extract_imports(ctx, "pkg/core.py", ctx.read_text("pkg/core.py")) == ["pkg/helpers.py"]
    deep = extract_imports(ctx, "pkg/sub/deep.py", ctx.read_text("pkg/sub/deep.py"))
    assert set(deep) == {"pkg/core.py", "pkg/sub/sibling.py"}


def test_third_party_imports_are_not_invented_as_nodes(tmp_path: Path):
    """An import that is not a file in this repository is external. Fabricating
    a node for it inflates fan-out and fills the graph with edges to nothing."""
    ctx = _package(tmp_path, {"app/__init__.py": "", "app/main.py": "import os\nimport requests\n"})
    assert extract_imports(ctx, "app/main.py", ctx.read_text("app/main.py")) == []


def test_src_layout_absolute_imports_resolve(tmp_path: Path):
    """An absolute import names the module as the interpreter sees it, not as the
    repository stores it. Without source-root detection this resolved nothing at
    all in src-layout projects — the most common Python layout."""
    ctx = _package(tmp_path, {
        "src/proj/__init__.py": "",
        "src/proj/core.py": "",
        "src/proj/app.py": "from proj.core import Thing\n",
    })
    assert ctx.source_roots() == ("", "src")
    assert extract_imports(ctx, "src/proj/app.py", ctx.read_text("src/proj/app.py")) == [
        "src/proj/core.py"
    ]


def test_importing_an_object_lands_on_its_module(tmp_path: Path):
    """`from pkg.mod import thing` names an object, not a module; the edge
    belongs on pkg/mod."""
    ctx = _package(tmp_path, {
        "pkg/__init__.py": "", "pkg/mod.py": "thing = 1\n",
        "pkg/user.py": "from pkg.mod import thing\n",
    })
    assert extract_imports(ctx, "pkg/user.py", ctx.read_text("pkg/user.py")) == ["pkg/mod.py"]


def test_package_import_resolves_to_its_init(tmp_path: Path):
    ctx = _package(tmp_path, {
        "pkg/__init__.py": "", "pkg/sub/__init__.py": "",
        "pkg/user.py": "from pkg import sub\nimport pkg.sub\n",
    })
    resolved = extract_imports(ctx, "pkg/user.py", ctx.read_text("pkg/user.py"))
    assert "pkg/sub/__init__.py" in resolved or "pkg/__init__.py" in resolved


def test_resolution_can_only_ever_name_a_walked_file(tmp_path: Path):
    """The safety property, stated as an invariant rather than a list of cases.

    Import specifiers come from untrusted repository content. Resolution returns
    a candidate only if it is already a member of the walked file set, so no
    specifier — however malformed — can name a path outside the project. These
    inputs are the ones worth naming explicitly, but the guarantee is structural,
    not a blocklist."""
    ctx = _package(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    hostile = [
        "." * 20 + "escape",          # more dots than the tree is deep
        "." * 5000 + "x",             # pathological depth
        "../../../../etc/passwd",
        "pkg/../../../etc/passwd",
        "\x00evil",
        "a" * 100_000,
        "",
        ".",
    ]
    for specifier in hostile:
        resolved = resolve_python_import(ctx, "pkg/a.py", specifier)
        assert resolved is None or resolved in ctx.known_files(), (
            f"{specifier[:40]!r} resolved to {resolved!r}, which is not a walked file"
        )


def test_resolution_stays_cheap_on_pathological_specifiers(tmp_path: Path):
    """It runs per import per file, so a hostile repository must not be able to
    make it expensive."""
    import time

    ctx = _package(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": ""})
    start = time.perf_counter()
    for _ in range(100):
        resolve_python_import(ctx, "pkg/a.py", "." * 5000 + "x")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"100 pathological resolutions took {elapsed:.2f}s"
