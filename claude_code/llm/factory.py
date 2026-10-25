from claude_code.config import config
from claude_code.observability.logger import get_logger
from claude_code.settings import provider_api_keys
from pydantic import SecretStr

logger = get_logger(__name__)


def _build_llm(provider: str, model: str, api_key: str | None = None):
    """Create one provider-specific LangChain model."""
    logger.info(f"Using LLM provider: {provider}, model: {model}")
    if provider == "ollama":
        import json
        import uuid
        from langchain_core.messages import AIMessage
        from langchain_ollama import ChatOllama

        class RobustChatOllama(ChatOllama):
            def _fix_message(self, msg):
                if isinstance(msg, AIMessage) and not msg.tool_calls:
                    if not isinstance(msg.content, str):
                        return msg
                    text = msg.content.strip()
                    if text.startswith("```"):
                        lines = text.splitlines()
                        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                            text = "\n".join(lines[1:-1]).strip()
                    if text.startswith("{"):
                        try:
                            data = json.loads(text)
                            if "name" in data and ("arguments" in data or "parameters" in data):
                                name = data["name"]
                                raw_args = data.get("arguments") or data.get("parameters") or {}
                                clean_args = {}
                                for k, v in raw_args.items():
                                    if isinstance(v, dict):
                                        clean_args[k] = v.get("value") or v.get("text") or v.get("query") or str(v)
                                    else:
                                        clean_args[k] = v
                                msg.tool_calls = [{"name": name, "args": clean_args, "id": str(uuid.uuid4()), "type": "tool_call"}]
                        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                            logger.debug("Could not normalize Ollama tool call: %s", exc)
                return msg

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                res = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
                for gen in res.generations:
                    self._fix_message(gen.message)
                return res

            async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
                res = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
                for gen in res.generations:
                    self._fix_message(gen.message)
                return res

        return RobustChatOllama(model=model)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if api_key:
            return ChatAnthropic(
                model_name=model,
                timeout=None,
                stop=None,
                api_key=SecretStr(api_key),
            )
        return ChatAnthropic(model_name=model, timeout=None, stop=None)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=SecretStr(api_key) if api_key else None)
    raise ValueError(
        f"Unsupported LLM provider {provider!r}. Use one of: anthropic, gemini, ollama, openai."
    )


def get_llm():
    """Return a model with same-key and model/provider fallback routing."""
    provider = config["llm"]["provider"].strip().lower()
    model = config["llm"]["model"]
    logger.info("Using primary LLM provider: %s, model: %s", provider, model)

    def build_key_pool(target_provider: str, target_model: str) -> list:
        keys = provider_api_keys(target_provider)
        if not keys:
            return [_build_llm(target_provider, target_model)]
        return [_build_llm(target_provider, target_model, key) for key in keys]

    primary_pool = build_key_pool(provider, model)
    primary = primary_pool[0]
    # A second key for the same provider/model is the first recovery option
    # when a provider rejects a request due to rate limit or quota exhaustion.
    fallbacks = primary_pool[1:]
    for fallback in config["llm"].get("fallbacks", []):
        if not isinstance(fallback, dict):
            continue
        fallback_provider = str(fallback.get("provider", "")).strip().lower()
        fallback_model = str(fallback.get("model", "")).strip()
        if not fallback_provider or not fallback_model:
            continue
        try:
            fallbacks.extend(build_key_pool(fallback_provider, fallback_model))
        except (ImportError, ValueError) as exc:
            logger.warning("Skipping invalid fallback %s/%s: %s", fallback_provider, fallback_model, exc)
    if fallbacks:
        logger.info("Configured %s LLM fallback model(s)", len(fallbacks))
        return primary.with_fallbacks(fallbacks)
    return primary


def get_embedder():
    """Return the right LangChain embedder based on config."""
    provider = config["embeddings"]["provider"].strip().lower()
    model = config["embeddings"]["model"]
    logger.info(f"Using embeddings provider: {provider}, model: {model}")
    if provider == "fastembed":
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
        model_name = model if model and "/" in model else "BAAI/bge-small-en-v1.5"
        return FastEmbedEmbeddings(model_name=model_name)
    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings  # pyright: ignore[reportMissingImports]
        return HuggingFaceEmbeddings(model_name=model)
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model)
    raise ValueError(
        f"Unsupported embeddings provider {provider!r}. Use one of: fastembed, huggingface, openai."
    )
