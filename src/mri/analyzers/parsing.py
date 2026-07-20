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
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from tree_sitter_language_pack import get_parser as _get_parser

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


def resolve_python_import(ctx: Any, importer_rel: str, specifier: str) -> str | None:
    """Turn a Python import into the repo-relative file it refers to.

    Returns None when the target is not a file in this repository — a
    third-party or stdlib import — because inventing a node for it inflates
    fan-out and leaves the graph full of edges to things that do not exist.

    Relative imports are why this function exists. `from .helpers import h` used
    to become the literal key "/helpers.py", and `from ..core import Thing`
    became "//core.py": nodes that match no file, so every intra-package edge
    vanished from the graph. Packages that use relative imports internally —
    which is most well-factored ones — therefore showed no cycles and near-zero
    internal coupling, and read as maximally stable. That is not noise; it is a
    metric that is confidently wrong in a way that correlates with code style.
    """
    known = ctx.known_files()
    dots = len(specifier) - len(specifier.lstrip("."))
    tail = specifier[dots:]

    if dots:
        # `.` is the importing module's own package, `..` its parent, and so on.
        base = PurePosixPath(importer_rel.replace("\\", "/")).parent
        for _ in range(dots - 1):
            base = base.parent
        parts = [p for p in (str(base).split("/") if str(base) != "." else []) if p]
        parts += tail.split(".") if tail else []
    else:
        parts = tail.split(".")

    if not parts:
        return None

    # `from pkg.mod import thing` names an object, not a module: falling back to
    # the parent lands the edge on pkg/mod rather than nowhere.
    stems = ["/".join(parts)]
    if len(parts) > 1:
        stems.append("/".join(parts[:-1]))

    # A relative import is already anchored at the importing file, so only an
    # absolute one needs the source-root prefixes.
    prefixes = ("",) if dots else ctx.source_roots()
    for stem in stems:
        for prefix in prefixes:
            base_path = f"{prefix}/{stem}" if prefix else stem
            for candidate in (f"{base_path}.py", f"{base_path}/__init__.py"):
                if candidate in known:
                    return candidate
    return None


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
                # Resolve against the files actually present rather than
                # rewriting dots into slashes and hoping. Anything that does not
                # resolve is a third-party or stdlib import and is dropped, not
                # turned into a node that matches nothing.
                imports = [
                    resolved
                    for module in imports
                    if (resolved := resolve_python_import(ctx, rel_path, module)) is not None
                ]
            if imports:
                return imports

    if suffix == ".py":
        out = []
        for m in _PY_IMPORT.finditer(content):
            module = m.group(1) or m.group(2)
            if not module:
                continue
            resolved = resolve_python_import(ctx, rel_path, module)
            if resolved is not None:
                out.append(resolved)
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
    "resolve_python_import",
    "HAS_TREE_SITTER",
    "extract_imports",
    "get_parser_for",
    "language_for_extension",
    "walk_imports",
]
