"""Shared tree-sitter access.

Parser construction is expensive, so parsers are cached per language. This lives
in one place because the analyzers used to each carry their own copy of this
logic — and `coupling` reached into `DependenciesAnalyzer._extract_imports`, a
private method, to re-derive an import graph that `dependencies` had already
built.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from tree_sitter_language_pack import get_parser as _get_parser  # type: ignore

    HAS_TREE_SITTER = True
except Exception:  # pragma: no cover - exercised only where the wheel is absent
    HAS_TREE_SITTER = False

# Source extension -> tree-sitter language name.
EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
}


def language_for_extension(ext: str) -> str | None:
    """tree-sitter language name for a file extension, or None if unsupported."""
    return EXT_TO_LANGUAGE.get(ext.lower())


@lru_cache(maxsize=32)
def get_parser_for(language: str) -> Any | None:
    """A cached parser for the language, or None when tree-sitter is absent."""
    if not HAS_TREE_SITTER:
        return None
    try:
        return _get_parser(language)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Import extraction — shared by the dependencies and coupling analyzers
# --------------------------------------------------------------------------

_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))", re.MULTILINE
)
_JS_IMPORT = re.compile(
    r"""(?:^\s*import\s+.*?from\s+['"]([^'"]+)['"]"""
    r"""|^\s*import\s+['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_QUOTED = re.compile(r"""['"]([^'"]+)['"]""")

# Node types that mark a file's top-level scope.
_ROOT_TYPES = ("module", "program", "source_file", "compilation_unit")


def _text_of(node: Any) -> str:
    """A node's source text.

    Taken from the node itself rather than by slicing the file with
    `start_byte`/`end_byte`: those are byte offsets, and slicing a `str` with
    them silently returns the wrong span as soon as the file contains any
    multi-byte character — an em dash in a comment above the import is enough.
    """
    raw = node.text
    return raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)


def walk_imports(root: Any, content: str) -> list[str]:
    """Collect import targets from a tree-sitter AST, iteratively.

    The recursive form hit Python's recursion limit on deeply nested code, so
    this uses an explicit stack and only descends through the top-level scope.

    Two grammars, two shapes. JavaScript and TypeScript name their target in a
    string literal (`import x from "./y"`), while Python names it bare
    (`import os`, `from pkg.mod import thing`). Reading only quoted strings —
    which is what this did — found nothing at all in Python: every file fell
    through to the regex fallback, so the AST path was dead code for the
    language the tool is mostly used on.
    """
    imports: list[str] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if node.type == "import_from_statement":
            # `from pkg.mod import a, b` — the module is the module_name field;
            # the names after `import` are members, not modules.
            module = node.child_by_field_name("module_name")
            if module is not None:
                imports.append(_text_of(module))
        elif node.type in ("import_statement", "import_declaration"):
            text = _text_of(node)
            quoted = [m.group(1) for m in _QUOTED.finditer(text)]
            if quoted:
                imports.extend(quoted)  # JS/TS
            else:
                imports.extend(  # Python
                    _text_of(child) for child in node.children if child.type == "dotted_name"
                )
        elif node.type in _ROOT_TYPES or node.parent is None or node.parent.type in _ROOT_TYPES:
            stack.extend(node.children)
    return imports


def extract_imports(ctx: Any, rel_path: str, content: str) -> list[str]:
    """Import paths declared by a file.

    Uses the AST when a parser is available and falls back to regex otherwise.
    The tree comes from the scan context, so a file parsed by one analyzer is
    not parsed again by the next.
    """
    suffix = Path(rel_path).suffix.lower()
    language = language_for_extension(suffix)

    if language:
        tree = ctx.parse_tree(rel_path, language)
        if tree is not None:
            imports = walk_imports(tree.root_node, content)
            if language == "python":
                # The AST yields dotted module names; downstream keys on paths.
                # Normalise to the same shape the regex fallback produces, or the
                # two paths would build different graphs for the same file.
                imports = [
                    module.replace(".", "/") + ".py"
                    for module in imports
                    if module.strip(".")  # skip bare relative markers like "."
                ]
            if imports:
                return imports

    if suffix == ".py":
        out = []
        for m in _PY_IMPORT.finditer(content):
            module = m.group(1) or m.group(2)
            # `from . import x` captures a bare "." — turning that into "/.py"
            # put a meaningless node into the dependency graph.
            if module and module.strip("."):
                out.append(module.replace(".", "/") + ".py")
        return out
    if suffix in (".js", ".ts", ".tsx", ".mjs", ".cjs"):
        return [
            module
            for m in _JS_IMPORT.finditer(content)
            if (module := m.group(1) or m.group(2) or m.group(3)) and module.startswith(".")
        ]
    return []


__all__ = [
    "EXT_TO_LANGUAGE",
    "HAS_TREE_SITTER",
    "extract_imports",
    "get_parser_for",
    "language_for_extension",
    "walk_imports",
]
