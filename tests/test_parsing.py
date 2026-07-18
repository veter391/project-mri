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
from mri.analyzers.parsing import extract_imports, get_parser_for, walk_imports


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
    source = "# a comment with an em dash — and another —\nimport pathlib\nfrom pkg.mod import x\n"
    rel = "multibyte.py"
    (tmp_path / rel).write_text(source, encoding="utf-8")
    found = extract_imports(_ctx(tmp_path), rel, source)
    # Exact equality: a shifted span produced entries like "thlib i.py", which
    # a substring check would not reliably catch (and "pathlib.py" itself
    # contains "thlib", which is how a sloppier assertion failed here).
    assert set(found) == {"pathlib.py", "pkg/mod.py"}


def test_ast_and_regex_paths_agree_on_shape(tmp_path: Path):
    """Downstream keys the dependency graph on these strings, so both paths must
    produce the same form or the two would build different graphs."""
    source = "import os\nfrom pkg.mod import thing\n"
    rel = "plain.py"
    (tmp_path / rel).write_text(source, encoding="utf-8")
    from_ast = extract_imports(_ctx(tmp_path), rel, source)

    from mri.analyzers.parsing import _PY_IMPORT

    from_regex = [
        (m.group(1) or m.group(2)).replace(".", "/") + ".py" for m in _PY_IMPORT.finditer(source)
    ]
    assert set(from_ast) == set(from_regex) == {"os.py", "pkg/mod.py"}


def test_relative_marker_is_not_emitted_as_a_module(tmp_path: Path):
    source = "from . import sibling\n"
    rel = "rel.py"
    (tmp_path / rel).write_text(source, encoding="utf-8")
    assert extract_imports(_ctx(tmp_path), rel, source) == []
