import logging
import os
# Set root logger to WARNING — suppresses noisy third-party library logs (OpenAI, httpcore etc.)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# Silence non-critical schema/function conversion warnings from LangChain Google GenAI
logging.getLogger("langchain_google_genai").setLevel(logging.ERROR)
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    # Set CLAUDE_CODE_DEBUG=true for parser-level and tool-level diagnostics.
    logger = logging.getLogger(name)
    debug_enabled = os.getenv("CLAUDE_CODE_DEBUG", "").lower() in {"1", "true", "yes"}
    logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    return logger
