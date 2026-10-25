"""Lightweight local import graph for supported workspace source files."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from claude_code.context.indexers.code_parser import get_source_files

_JS_IMPORT = re.compile(r"(?:import|export)\s+(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']|require\(\s*[\"']([^\"']+)[\"']\s*\)")
_MAX_NODES = 140
_MAX_EDGES = 260


def _python_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return []
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
    return modules


def _javascript_imports(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [first or second for first, second in _JS_IMPORT.findall(text)]


def _resolve_module(source: Path, module: str, root: Path, known: set[str]) -> str | None:
    if module.startswith("."):
        base = source.parent / module
        candidates = [base, *(base.with_suffix(ext) for ext in (".py", ".js", ".jsx", ".ts", ".tsx"))]
        candidates.extend(base / f"index{ext}" for ext in (".js", ".ts", ".tsx"))
        for candidate in candidates:
            try:
                relative = candidate.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            if relative in known:
                return relative
        return None
    python_candidate = Path(*module.split(".")).with_suffix(".py").as_posix()
    if python_candidate in known:
        return python_candidate
    package_candidate = (Path(*module.split(".")) / "__init__.py").as_posix()
    return package_candidate if package_candidate in known else None


def build_code_graph(workspace: str) -> dict:
    """Return bounded nodes/edges for Python and JS/TS workspace imports."""
    root = Path(workspace).resolve()
    paths = [Path(path) for path in get_source_files(str(root))]
    known = {path.relative_to(root).as_posix() for path in paths}
    nodes = sorted(known)[:_MAX_NODES]
    visible = set(nodes)
    edges = []
    for path in paths:
        source = path.relative_to(root).as_posix()
        if source not in visible:
            continue
        imports = _python_imports(path) if path.suffix == ".py" else _javascript_imports(path) if path.suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"} else []
        for module in imports:
            target = _resolve_module(path, module, root, known)
            if target and target in visible and target != source:
                edges.append({"source": source, "target": target})
    unique_edges = list({(edge["source"], edge["target"]): edge for edge in edges}.values())[:_MAX_EDGES]
    return {
        "nodes": [{"id": node, "label": Path(node).name, "group": Path(node).parts[0] if "/" in node else "root"} for node in nodes],
        "edges": unique_edges,
        "truncated": len(known) > len(nodes),
    }
