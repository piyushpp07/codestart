from claude_code.config import config
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)


def get_retriever(provider: str | None = None):
    """Factory: Return the retrieval function for the specified or configured vectorstore."""
    provider = (provider or config.get("vectorstore", {}).get("provider", "pinecone")).lower()
    logger.info(f"Using retriever factory for provider: {provider}")

    if provider in ("pinecone_hybrid", "hybrid_pinecone", "hybrid"):
        from claude_code.context.retrievers.hybrid_pinecone import retrieve
        return retrieve
    if provider == "pinecone":
        from claude_code.context.retrievers.semantic_pinecone import retrieve
        return retrieve
    from claude_code.context.retrievers.sementic_faiss import retrieve
    return retrieve
