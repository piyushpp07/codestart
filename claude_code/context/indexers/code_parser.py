from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from tree_sitter import Language, Parser

from claude_code.observability.logger import get_logger

logger = get_logger(__name__)

# Maps file extension → tree-sitter language name.
# Each language is loaded on demand from its own package.
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sh": "bash",
}

# Text/config files have no meaningful AST — we chunk them by line count instead.
TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".jsonc",
    ".toml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".vue",
    ".svelte",
    ".xml",
    ".svg",
    ".ini",
    ".cfg",
}
TEXT_FILENAMES = {"dockerfile", "makefile"}
ALL_EXTENSIONS = set(EXTENSION_TO_LANGUAGE.keys()) | TEXT_EXTENSIONS

# Sliding window settings for text files and AST fallback.
CHUNK_SIZE = 50
CHUNK_OVERLAP = 10
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024

# Tree-sitter node type names that correspond to a named, indexable block.
BLOCK_NODE_TYPES = {
    "function_definition", "function_declaration", "method_definition",
    "arrow_function", "class_definition", "class_declaration",
    "method_declaration", "constructor_declaration", "interface_declaration",
    "function_item",     # Rust
    "func_declaration",  # Go
}


def _load_language(name: str) -> Language:
    """
    Lazily import the appropriate tree-sitter-<language> package and return
    the Language object.  Results are cached so each grammar is built once.
    """
    return _cached_language(name)


@cache
def _cached_language(name: str) -> Language:
    """Import and cache a Language object by logical name."""
    if name == "python":
        import tree_sitter_python as python_module

        return Language(python_module.language())
    if name in ("javascript", "jsx"):
        import tree_sitter_javascript as javascript_module

        return Language(javascript_module.language())
    if name == "typescript":
        import tree_sitter_typescript as typescript_module

        return Language(typescript_module.language_typescript())
    if name == "tsx":
        import tree_sitter_typescript as tsx_module

        return Language(tsx_module.language_tsx())
    if name == "java":
        import tree_sitter_java as java_module

        return Language(java_module.language())
    if name == "go":
        import tree_sitter_go as go_module

        return Language(go_module.language())
    if name == "rust":
        import tree_sitter_rust as rust_module

        return Language(rust_module.language())
    if name == "cpp":
        import tree_sitter_cpp as cpp_module

        return Language(cpp_module.language())
    if name == "c":
        import tree_sitter_c as c_module

        return Language(c_module.language())
    if name == "c_sharp":
        import tree_sitter_c_sharp as c_sharp_module

        return Language(c_sharp_module.language())
    if name == "ruby":
        import tree_sitter_ruby as ruby_module

        return Language(ruby_module.language())
    if name == "php":
        import tree_sitter_php as php_module

        return Language(php_module.language_php())
    if name == "swift":
        import tree_sitter_swift as swift_module

        # tree-sitter-swift stubs return int, which triggers deprecated Language(int) overload; cast to object
        return Language(cast(object, swift_module.language()))
    if name == "kotlin":
        import tree_sitter_kotlin as kotlin_module

        return Language(kotlin_module.language())
    if name == "bash":
        import tree_sitter_bash as bash_module

        return Language(bash_module.language())
    raise ValueError(f"No tree-sitter grammar registered for language: {name!r}")


def get_parser(language_name: str) -> Parser:
    """Return a configured Parser for the given language name."""
    lang = _load_language(language_name)
    return Parser(lang)


@dataclass
class ParsedChunk:
    name: str
    type: str        # "function" | "class" | "block"
    content: str
    source: str
    start_line: int
    end_line: int


def parse_file(filepath: str) -> list[ParsedChunk]:
    """Entry point — routes to AST parsing or sliding window based on file type."""
    path = Path(filepath)
    if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
        logger.warning("Skipping %s: larger than %s bytes", filepath, MAX_SOURCE_FILE_BYTES)
        return []
    source = path.read_text(encoding="utf-8", errors="ignore")
    if not source.strip():
        logger.debug("Empty or whitespace-only file: %s", filepath)
        return []

    ext = Path(filepath).suffix.lower()
    if ext in TEXT_EXTENSIONS or path.name.lower() in TEXT_FILENAMES:
        lines = source.splitlines()
        return _sliding_window(lines, filepath)
    language_name = EXTENSION_TO_LANGUAGE.get(ext)
    if not language_name:
        raise ValueError(f"Unsupported file type: {ext}")
    return _parse_with_treesitter(source, filepath, language_name)


def _parse_with_treesitter(source: str, filepath: str, language_name: str) -> list[ParsedChunk]:
    """Parse source with the appropriate tree-sitter grammar and extract named blocks."""
    logger.debug("Parsing %s file: %s", language_name, filepath)
    parser = get_parser(language_name)
    tree = parser.parse(source.encode("utf-8"))
    lines = source.splitlines()
    chunks = []
    _walk(tree.root_node, filepath, chunks, depth=0)
    # If the AST yielded nothing (e.g. a file with only imports), fall back to line chunks
    if not chunks:
        logger.debug("No AST blocks found in %s; falling back to sliding window", filepath)
        return _sliding_window(lines, filepath)
    logger.debug("Parsed %s chunks from %s", len(chunks), filepath)
    return chunks


def _walk(node, filepath: str, chunks: list[ParsedChunk], depth: int) -> None:
    """
    Recursively walk the AST. When a named block node is found, record it and stop
    descending — this keeps chunks at the top level and avoids duplicating nested functions.
    """
    if node.type in BLOCK_NODE_TYPES:
        name = _extract_name(node)
        content = node.text.decode("utf-8", errors="replace")
        chunk_type = "class" if "class" in node.type else "function"
        chunks.append(ParsedChunk(
            name=name,
            type=chunk_type,
            content=content,
            source=filepath,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
        ))
        logger.debug(
            f"  Found {chunk_type} '{name}' "
            f"(lines {node.start_point[0] + 1}-{node.end_point[0] + 1})"
        )
        return  # stop here — don't index nested functions/classes as separate chunks
    for child in node.children:
        _walk(child, filepath, chunks, depth + 1)


def _extract_name(node) -> str:
    """Find the identifier child of a block node and return its text as the chunk name."""
    for child in node.children:
        if child.type in ("identifier", "name", "property_identifier"):
            return child.text.decode("utf-8", errors="replace")
    return node.type  # fallback to node type if no name found


def _sliding_window(lines: list[str], filepath: str) -> list[ParsedChunk]:
    """
    Split lines into overlapping fixed-size chunks.
    Used for text files and as a fallback when AST parsing finds nothing.
    """
    if not lines:
        return []
    chunks = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for i, start in enumerate(range(0, len(lines), step)):
        end = min(start + CHUNK_SIZE, len(lines))
        text = "\n".join(lines[start:end]).strip()
        if text:
            chunks.append(ParsedChunk(
                name=f"chunk_{i}",
                type="block",
                content=text,
                source=filepath,
                start_line=start + 1,
                end_line=end,
            ))
        if end == len(lines):
            break
    logger.debug("Parsed %s chunks from %s", len(chunks), filepath)
    return chunks


def get_source_files(repo_path: str, skip_dirs: list[str] | None = None) -> list[str]:
    """Recursively find all indexable source files under repo_path, skipping build/env dirs."""
    skip = set(
        skip_dirs
        or [
            ".venv",
            "venv",
            ".faiss",
            ".chroma",
            ".memory",
            "__pycache__",
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
            "dist",
            "build",
        ]
    )
    files = [
        str(path) for path in Path(repo_path).rglob("*")
        if path.is_file()
        and (path.suffix.lower() in ALL_EXTENSIONS or path.name.lower() in TEXT_FILENAMES)
        and not any(part in skip for part in path.parts)
    ]
    logger.debug("Found %s source files in %s", len(files), repo_path)
    return files
