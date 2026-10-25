from pathlib import Path
from typing import Any, cast

from pinecone_text.sparse import BM25Encoder
from pinecone_text.hybrid import hybrid_convex_scale

from claude_code.context.indexers.hybrid_pinecone import get_namespace_for_repo, get_pinecone_hybrid_index
from claude_code.llm.factory import get_embedder
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def retrieve(query: str, k: int = 5, alpha: float = 0.7, repo_path: str | None = None) -> list[dict]:
    """
    Perform Hybrid Search (Dense Embeddings + BM25 Sparse Vectors) in Pinecone Cloud.
    alpha = 1.0 -> Pure semantic vector search
    alpha = 0.0 -> Pure keyword BM25 search
    alpha = 0.7 -> Balanced hybrid search (default)
    """
    try:
        index = get_pinecone_hybrid_index()
        target_path = repo_path or str(Path.cwd())
        namespace = get_namespace_for_repo(target_path)
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone hybrid retriever: {e}")
        return []

    embedder = get_embedder()
    bm25 = BM25Encoder.default()

    # 1. Encode dense query vector
    dense_vec = embedder.embed_query(query)

    # 2. Encode sparse BM25 query vector
    encoded_queries = cast(list[dict[str, list[int] | list[float]]], bm25.encode_queries([query]))
    sparse_vec = encoded_queries[0]

    # 3. Apply convex scaling with alpha
    hd, hs = hybrid_convex_scale(dense_vec, sparse_vec, alpha=alpha)

    logger.info(f"Querying Pinecone Hybrid (namespace: {namespace}, alpha: {alpha}, k: {k}) for: '{query}'")
    try:
        results: Any = index.query(
            vector=hd,
            sparse_vector=cast(Any, hs),
            top_k=k,
            namespace=namespace,
            include_metadata=True,
        )
    except Exception as e:
        logger.error(f"Pinecone hybrid search query failed: {e}")
        return []

    chunks = []
    for match in results.matches:
        meta = match.metadata or {}
        chunks.append({
            "content": meta.get("text", ""),
            "source": meta.get("source", "unknown"),
            "name": meta.get("name", "unknown"),
            "type": meta.get("type", "block"),
            "start_line": meta.get("start_line", "?"),
            "end_line": meta.get("end_line", "?"),
            "distance": float(match.score),
        })
        logger.debug(
            f"  Retrieved {meta.get('type')} '{meta.get('name')}' from {meta.get('source')} (score: {match.score:.4f})"
        )

    logger.info(f"Retrieved {len(chunks)} chunks from Pinecone Hybrid")
    return chunks
