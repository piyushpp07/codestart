from pathlib import Path
from typing import Any

from claude_code.context.indexers.semantic_pinecone import get_namespace_for_repo, load_index
from claude_code.llm.factory import get_embedder
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def retrieve(query: str, k: int = 5, repo_path: str | None = None) -> list[dict]:
    """Embed the query and find top-k similar chunks in a Pinecone namespace."""
    try:
        target_path = repo_path or str(Path.cwd())
        index = load_index(target_path)
        namespace = get_namespace_for_repo(target_path)
        vector = get_embedder().embed_query(query)
    except Exception as e:
        logger.error(f"Failed to connect to Pinecone index: {e}")
        return []

    logger.info(f"Retrieving top {k} chunks from Pinecone for query: '{query}'")
    try:
        results: Any = index.query(
            vector=vector,
            top_k=k,
            namespace=namespace,
            include_metadata=True,
        )
    except Exception as e:
        logger.error(f"Error querying Pinecone: {e}")
        return []

    chunks = []
    for match in results.matches:
        meta = match.metadata or {}
        chunks.append({
            "content": meta.get("text", ""),
            "source": meta.get("source"),
            "name": meta.get("name"),
            "type": meta.get("type"),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "distance": float(match.score),
        })
        logger.debug(
            f"  Retrieved {meta.get('type')} '{meta.get('name')}' from {meta.get('source')} (score: {match.score:.4f})"
        )

    logger.info(f"Retrieved {len(chunks)} chunks from Pinecone")
    return chunks
