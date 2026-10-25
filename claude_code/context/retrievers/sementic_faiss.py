from claude_code.context.indexers.semantic_indexer import load_index
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def retrieve(query: str, k: int = 5) -> list[dict]:
    """Embed the query and find the k most similar chunks in the FAISS index.
    Returns a list of results with content, metadata fields, and distance."""
    try:
        vectorstore = load_index()
    except FileNotFoundError as e:
        logger.error(f"Failed to load FAISS index: {e}")
        return []

    logger.info(f"Retrieving top {k} chunks for query: '{query}'")
    results = vectorstore.similarity_search_with_score(query, k=k)

    chunks = []
    for doc, dist in results:
        meta = doc.metadata or {}
        chunks.append({
            "content": doc.page_content,
            "source": meta.get("source"),
            "name": meta.get("name"),
            "type": meta.get("type"),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "distance": float(dist),  # FAISS L2 distance: lower = more similar
        })
        logger.debug(
            f"  Retrieved {meta.get('type')} '{meta.get('name')}' from {meta.get('source')} (distance: {dist:.4f})"
        )

    logger.info(f"Retrieved {len(chunks)} chunks")
    return chunks
