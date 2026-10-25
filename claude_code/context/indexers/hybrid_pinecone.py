import os
import hashlib
from pathlib import Path
from typing import Any, cast
from pinecone import Pinecone
from pinecone_text.sparse import BM25Encoder

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
    clean_name = "".join(c if c.isalnum() else "-" for c in repo_name)
    return f"{clean_name}-{path_hash}"


def get_pinecone_hybrid_index():
    """Return Pinecone Index instance configured for hybrid search (dotproduct metric)."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found in environment or .env")
    index_name = os.getenv("PINECONE_HYBRID_INDEX_NAME") or config.get("pinecone", {}).get("hybrid_index_name", "hybrid")
    pc = Pinecone(api_key=api_key)
    return pc.Index(index_name)


def index_codebase(repo_path: str):
    """
    Parse source files, generate dense vectors (FastEmbed) + BM25 sparse vectors,
    and upload hybrid vectors to Pinecone Cloud.
    """
    embedder = get_embedder()
    bm25 = BM25Encoder.default()
    index = get_pinecone_hybrid_index()
    namespace = get_namespace_for_repo(repo_path)

    logger.info(f"Starting Pinecone Hybrid indexing of {repo_path} (namespace: {namespace})")
    files = get_source_files(repo_path)

    parsed_chunks = []
    for filepath in files:
        try:
            chunks = parse_file(filepath)
        except (OSError, SyntaxError, ValueError) as e:
            logger.error(f"Skipping {filepath}: {e}")
            continue

        for chunk in chunks:
            parsed_chunks.append(chunk)

    if not parsed_chunks:
        logger.warning(f"No indexable chunks found under {repo_path}. Skipping upsert.")
        return index

    texts = [c.content for c in parsed_chunks]
    logger.info(f"Generating dense embeddings for {len(texts)} chunks...")
    dense_vectors = embedder.embed_documents(texts)

    logger.info(f"Generating BM25 sparse vectors for {len(texts)} chunks...")
    sparse_vectors = cast(list[dict[str, Any]], bm25.encode_documents(texts))

    vectors_to_upsert = []
    for i, chunk in enumerate(parsed_chunks):
        doc_id = f"{chunk.source}:{chunk.start_line}:{chunk.name}:{i}"
        vectors_to_upsert.append({
            "id": doc_id,
            "values": dense_vectors[i],
            "sparse_values": sparse_vectors[i],
            "metadata": {
                "text": chunk.content,
                "source": chunk.source,
                "name": chunk.name,
                "type": chunk.type,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            },
        })

    # Upsert in batches of 50
    batch_size = 50
    for idx in range(0, len(vectors_to_upsert), batch_size):
        batch = vectors_to_upsert[idx : idx + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
        logger.debug(f"Upserted batch {idx // batch_size + 1} ({len(batch)} vectors)")

    logger.info(f"Hybrid indexing complete: {len(vectors_to_upsert)} chunks uploaded to Pinecone ({namespace}).")
    return index


def load_index(repo_path: str | None = None):
    """Return the Pinecone hybrid index for the target repo."""
    return get_pinecone_hybrid_index()
