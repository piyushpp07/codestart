from claude_code.config import config
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def get_indexer(provider: str | None = None):
    """Factory: Return the indexing function for the specified or configured vectorstore."""
    provider = (provider or config.get("vectorstore", {}).get("provider", "pinecone")).lower()
    logger.info(f"Using indexer factory for provider: {provider}")

    if provider in ("pinecone_hybrid", "hybrid_pinecone", "hybrid"):
        from claude_code.context.indexers.hybrid_pinecone import index_codebase
        return index_codebase
    if provider == "pinecone":
        from claude_code.context.indexers.semantic_pinecone import index_codebase
        return index_codebase
    from claude_code.context.indexers.semantic_indexer import index_codebase
    return index_codebase


def get_index_loader(provider: str | None = None):
    """Factory: Return the index loader function for the specified or configured vectorstore."""
    provider = (provider or config.get("vectorstore", {}).get("provider", "pinecone")).lower()

    if provider in ("pinecone_hybrid", "hybrid_pinecone", "hybrid"):
        from claude_code.context.indexers.hybrid_pinecone import load_index
        return load_index
    if provider == "pinecone":
        from claude_code.context.indexers.semantic_pinecone import load_index
        return load_index
    from claude_code.context.indexers.semantic_indexer import load_index
    return load_index
