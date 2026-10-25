"""Local FAISS indexing with a file manifest for incremental updates."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from claude_code.config import config
from claude_code.context.indexers.code_parser import get_source_files, parse_file
from claude_code.llm.factory import get_embedder
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)
ProgressCallback = Callable[[int, int, str], None]


def _paths() -> tuple[Path, str, Path, Path]:
    persist_dir = Path(config["faiss"]["persist_dir"])
    index_name = config["faiss"]["index_name"]
    index_path = persist_dir / f"{index_name}.faiss"
    manifest_path = persist_dir / f"{index_name}.manifest.json"
    return persist_dir, index_name, index_path, manifest_path


def _file_hash(filepath: str) -> str:
    return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()


def _chunk_id(filepath: str, number: int, content: str) -> str:
    digest = hashlib.sha256(f"{filepath}:{number}:{content}".encode("utf-8")).hexdigest()
    return f"chunk-{digest}"


def _load_manifest(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _documents_for_files(
    files: list[str], progress_callback: ProgressCallback | None = None
) -> tuple[list[Document], dict[str, list[str]]]:
    docs: list[Document] = []
    chunk_ids: dict[str, list[str]] = {}
    for position, filepath in enumerate(files, start=1):
        chunk_ids[filepath] = []
        try:
            chunks = parse_file(filepath)
        except (OSError, SyntaxError, ValueError) as exc:
            logger.error("Skipping %s: %s", filepath, exc)
            continue
        ids: list[str] = []
        for number, chunk in enumerate(chunks):
            document_id = _chunk_id(filepath, number, chunk.content)
            ids.append(document_id)
            docs.append(
                Document(
                    page_content=chunk.content,
                    metadata={
                        "source": chunk.source,
                        "name": chunk.name,
                        "type": chunk.type,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                    },
                )
            )
        chunk_ids[filepath] = ids
        if progress_callback:
            progress_callback(position, len(files), f"Indexing {Path(filepath).name}")
    return docs, chunk_ids


def _load_with_embedder(embedder, persist_dir: Path, index_name: str) -> FAISS:
    return FAISS.load_local(
        folder_path=str(persist_dir),
        embeddings=embedder,
        index_name=index_name,
        allow_dangerous_deserialization=True,
    )


def index_codebase(
    repo_path: str, force: bool = False, progress_callback: ProgressCallback | None = None
) -> FAISS:
    """Index changed source files only; use ``force`` to rebuild the whole FAISS index."""
    embedder = get_embedder()
    persist_dir, index_name, index_path, manifest_path = _paths()
    files = get_source_files(repo_path)
    if not files:
        raise ValueError(f"No indexable source files found under {repo_path}")
    file_hashes = {filepath: _file_hash(filepath) for filepath in files}
    manifest = _load_manifest(manifest_path)

    can_update = index_path.is_file() and manifest is not None and not force
    if can_update:
        assert manifest is not None
        vectorstore = _load_with_embedder(embedder, persist_dir, index_name)
        previous_hashes = manifest.get("files", {})
        previous_chunk_ids = manifest.get("file_chunk_ids", {})
        changed_files = [
            filepath for filepath, digest in file_hashes.items() if previous_hashes.get(filepath) != digest
        ]
        removed_files = set(previous_hashes) - set(file_hashes)
        if not changed_files and not removed_files:
            logger.info("FAISS index is current; no files changed")
            if progress_callback:
                progress_callback(len(files), len(files), "Index is up to date")
            return vectorstore

        ids_to_delete = [
            chunk_id
            for filepath in [*changed_files, *removed_files]
            for chunk_id in previous_chunk_ids.get(filepath, [])
        ]
        if ids_to_delete:
            vectorstore.delete(ids_to_delete)
        docs, changed_chunk_ids = _documents_for_files(changed_files, progress_callback)
        if docs:
            new_ids = [chunk_id for filepath in changed_files for chunk_id in changed_chunk_ids[filepath]]
            vectorstore.add_documents(docs, ids=new_ids)

        next_chunk_ids = {
            filepath: ids
            for filepath, ids in previous_chunk_ids.items()
            if filepath in file_hashes and filepath not in changed_files
        }
        next_chunk_ids.update(changed_chunk_ids)
        vectorstore.save_local(folder_path=str(persist_dir), index_name=index_name)
        _save_manifest(
            manifest_path,
            {"files": file_hashes, "file_chunk_ids": next_chunk_ids},
        )
        logger.info("Incrementally indexed %s changed and %s removed files", len(changed_files), len(removed_files))
        return vectorstore

    logger.info("Building FAISS index from %s source files", len(files))
    docs, chunk_ids = _documents_for_files(files, progress_callback)
    if not docs:
        raise ValueError(f"No indexable chunks found under {repo_path}")
    document_ids = [chunk_id for filepath in files for chunk_id in chunk_ids[filepath]]
    vectorstore = FAISS.from_documents(docs, embedder, ids=document_ids)
    persist_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(folder_path=str(persist_dir), index_name=index_name)
    _save_manifest(manifest_path, {"files": file_hashes, "file_chunk_ids": chunk_ids})
    logger.info("FAISS indexing complete. %s chunks saved to %s", len(docs), persist_dir)
    return vectorstore


def load_index() -> FAISS:
    """Load an existing FAISS index from disk. Raises if it has not been built."""
    persist_dir, index_name, index_path, _ = _paths()
    if not index_path.is_file():
        raise FileNotFoundError(
            f"No FAISS index found at '{index_path}'. Run index_codebase() first."
        )
    logger.info("Loading FAISS index from %s", persist_dir)
    return _load_with_embedder(get_embedder(), persist_dir, index_name)
