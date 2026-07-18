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


def walk_imports(root: Any, content: str) -> list[str]:
    """Collect import strings from a tree-sitter AST, iteratively.

    The recursive form hit Python's recursion limit on deeply nested code, so
    this uses an explicit stack and only descends through the top-level scope.
    """
    imports: list[str] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if node.type in ("import_statement", "import_declaration"):
            text = content[node.start_byte : node.end_byte]
            imports.extend(m.group(1) for m in _QUOTED.finditer(text))
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
            if imports:
                return imports

    if suffix == ".py":
        out = []
        for m in _PY_IMPORT.finditer(content):
            module = m.group(1) or m.group(2)
            if module:
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
