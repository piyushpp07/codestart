from claude_code.mcp.mcp_config import load_mcp_configs
from claude_code.observability.logger import get_logger
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = get_logger(__name__)

async def get_mcp_tools() -> list:
    """Connect to all configured MCP servers and return their tools."""
    try:
        configs = load_mcp_configs()
        if not configs:
            logger.info("No MCP servers configured")
            return []
        logger.info(f"Connecting to {len(configs)} MCP servers: {list(configs.keys())}")
        client = MultiServerMCPClient(configs)
        tools = await client.get_tools()
        logger.info(f"Successfully loaded {len(tools)} tools from MCP servers")
        return tools
    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        return []
