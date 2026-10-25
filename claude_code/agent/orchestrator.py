from langchain_core.runnables import RunnableConfig
from rich.console import Console
from typing import Any

from claude_code.agent.factory import AgentMode, build_agent
from claude_code.context.retrievers.factory import get_retriever
from claude_code.memory.session import get_current_session
from claude_code.observability.logger import get_logger

logger = get_logger(__name__)
console = Console()

_agents: dict[AgentMode, Any] = {}


def reset_agents() -> None:
    """Discard cached agents after local model settings change."""
    _agents.clear()


async def get_or_build_agent(mode: AgentMode):
    """Cache one compiled agent per permission mode."""
    if mode not in _agents:
        _agents[mode] = await build_agent(mode)
    return _agents[mode]


async def handle_query(
    query: str, thread_id: str | None = None, mode: AgentMode = "write"
) -> str:
    """Retrieves relevant code context, runs the agent with streaming feedback, and returns response."""
    try:
        logger.info(f"Running query: {query}")
        thread_id = thread_id or get_current_session()
        retrieve = get_retriever()
        chunks = retrieve(query, k=5)
        context_str = ""
        if chunks:
            formatted_chunks = []
            for chunk in chunks:
                formatted_chunks.append(
                    f"File: {chunk['source']} (lines {chunk['start_line']}-{chunk['end_line']})\n"
                    f"Name: {chunk['name']} ({chunk['type']})\n"
                    f"Code:\n{chunk['content']}"
                )
            context_str = "\n\n---\n\n".join(formatted_chunks)

        if context_str:
            prompt = (
                f"User Question: {query}\n\n"
                f"Relevant Code Chunks from Codebase:\n"
                f"```\n{context_str}\n```\n\n"
                f"Based on the code above, directly answer the user's question with specific explanations, citing file names and line numbers."
            )
        else:
            prompt = query

        agent = await get_or_build_agent(mode)
        agent_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        final_content = ""
        with console.status("[bold cyan]Agent is thinking and processing...[/bold cyan]", spinner="dots") as status:
            async for event in agent.astream({"messages": [{"role": "user", "content": prompt}]}, agent_config):
                for node_name, node_output in event.items():
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tool_name = tc.get("name", "tool")
                                status.update(f"[bold yellow]Executing tool: {tool_name}...[/bold yellow]")
                                console.print(f"  [dim]→ Calling tool:[/dim] [bold cyan]{tool_name}[/bold cyan]")
                        elif hasattr(msg, "name") and msg.name:
                            status.update("[bold cyan]Agent analyzing tool result...[/bold cyan]")
                        elif hasattr(msg, "content") and msg.content and node_name == "agent":
                            content = msg.content
                            if isinstance(content, list):
                                text_parts = [
                                    str(part["text"])
                                    for part in content
                                    if isinstance(part, dict) and "text" in part
                                ]
                                final_content = "".join(text_parts) if text_parts else str(content)
                            else:
                                final_content = str(content)

        if not final_content:
            final_content = "Agent finished execution without text output."

        return final_content

    except Exception as e:
        logger.error(f"Error running query: {e}")
        return f"Error executing query: {e}"
