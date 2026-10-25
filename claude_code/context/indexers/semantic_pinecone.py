import os
import hashlib
from pathlib import Path
from pinecone import Pinecone

from claude_code.config import config
from claude_code.context.indexers.code_parser import parse_file, get_source_files
from claude_code.llm.factory import get_embedder
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def get_namespace_for_repo(repo_path: str) -> str:
    """Generate a clean namespace from the repo folder name and path hash."""
    path_obj = Path(repo_path).resolve()
    repo_name = path_obj.name.lower()
    path_hash = hashlib.md5(str(path_obj).encode("utf-8")).hexdigest()[:8]
    # Pinecone namespaces can be alphanumeric + dashes
    clean_name = "".join(c if c.isalnum() else "-" for c in repo_name)
    return f"{clean_name}-{path_hash}"


def get_pinecone_index():
    """Return the configured native Pinecone index."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found in environment or .env")
    index_name = os.getenv("PINECONE_INDEX_NAME") or config.get("pinecone", {}).get(
        "index_name", "default"
    )
    return Pinecone(api_key=api_key).Index(index_name)


def index_codebase(repo_path: str):
    """
    Parse source files in repo_path, embed each chunk, and upload to Pinecone Cloud.
    Uses a repository-specific namespace so multiple projects can share the same index.
    """
    embedder = get_embedder()
    index = get_pinecone_index()
    namespace = get_namespace_for_repo(repo_path)

    logger.info(f"Starting Pinecone cloud indexing of {repo_path} (namespace: {namespace})")
    files = get_source_files(repo_path)

    chunks_to_index = []
    for filepath in files:
        try:
            chunks = parse_file(filepath)
        except (OSError, SyntaxError, ValueError) as e:
            logger.error(f"Skipping {filepath}: {e}")
            continue

        for chunk in chunks:
            chunks_to_index.append(chunk)
            logger.debug(f"  Queued {chunk.type} '{chunk.name}' from {filepath}")

    if not chunks_to_index:
        logger.warning(f"No indexable chunks found under {repo_path}. Skipping upload.")
        return load_index(repo_path)

    logger.info("Generating embeddings for %s chunks...", len(chunks_to_index))
    vectors = embedder.embed_documents([chunk.content for chunk in chunks_to_index])
    records = []
    for number, (chunk, vector) in enumerate(zip(chunks_to_index, vectors, strict=True)):
        record_id = f"{chunk.source}:{chunk.start_line}:{chunk.name}:{number}"
        records.append(
            {
                "id": record_id,
                "values": vector,
                "metadata": {
                    "text": chunk.content,
                    "source": chunk.source,
                    "name": chunk.name,
                    "type": chunk.type,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                },
            }
        )

    for start in range(0, len(records), 50):
        index.upsert(vectors=records[start : start + 50], namespace=namespace)
    logger.info("Pinecone indexing complete. %s chunks stored in cloud.", len(records))
    return index


def load_index(repo_path: str | None = None):
    """Connect to the configured native Pinecone index."""
    return get_pinecone_index()
