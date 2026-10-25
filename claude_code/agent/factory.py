from typing import Literal

from langgraph.prebuilt import create_react_agent

from claude_code.agent.tools import search_codebase
from claude_code.agent.tools.change_tools import (
    show_staged_diff,
    stage_delete_file,
    stage_edit_file,
    stage_write_file,
)
from claude_code.agent.tools.filesystem_tools import (
    append_file,
    delete_file,
    edit_file,
    file_exists,
    list_directory,
    read_file,
    write_file,
)
from claude_code.agent.tools.terminal_tools import run_command, run_in_directory
from claude_code.llm.factory import get_llm
from claude_code.mcp import get_mcp_tools
from claude_code.memory.short_term import get_checkpointer
from claude_code.observability.logger import get_logger
from claude_code.skills.skill_tools import build_skills_prompt, load_skill

logger = get_logger(__name__)

AgentMode = Literal["read", "stage", "write"]

SYSTEM_PROMPT = """You are an expert senior software engineer with deep knowledge of the codebase.
- Use search_codebase and the read-only filesystem tools to inspect code before answering or changing it.
- Only use GitHub tools when the user explicitly requests remote GitHub work.
- Answer directly with concrete files, decisions, and verification results.
- If a requested file or function cannot be found, state that clearly."""

MODE_INSTRUCTIONS: dict[AgentMode, str] = {
    "read": """You are in read-only mode. Do not modify files, run shell commands, or call tools that change state. Analyze, plan, or review only.""",
    "stage": """You are in staged-edit mode. Do not call write_file, edit_file, append_file, delete_file, terminal tools, or MCP write tools. After inspecting files, use stage_write_file, stage_edit_file, and stage_delete_file to prepare changes. Staged changes are not written to disk until the user runs /apply. Call show_staged_diff before your final response and summarize the proposed changes.""",
    "write": """You may make workspace changes with the filesystem tools when the user explicitly asks. Read a file before editing it, keep changes focused, and run relevant checks when practical.""",
}


async def build_agent(mode: AgentMode = "write"):
    """Create an agent with tools appropriate for read, staged, or direct-write work."""
    llm = get_llm()
    skills_prompt = build_skills_prompt()
    prompt = f"{SYSTEM_PROMPT}\n\n{MODE_INSTRUCTIONS[mode]}"
    if skills_prompt:
        prompt = f"{prompt}\n\n{skills_prompt}"

    read_tools = [search_codebase, load_skill, read_file, list_directory, file_exists]
    if mode == "read":
        tools = read_tools
    elif mode == "stage":
        tools = read_tools + [stage_write_file, stage_edit_file, stage_delete_file, show_staged_diff]
    else:
        # MCP integrations are retained only for explicit direct-write workflows.
        mcp_tools = await get_mcp_tools()
        tools = read_tools + [
            write_file,
            edit_file,
            append_file,
            delete_file,
            run_command,
            run_in_directory,
            *mcp_tools,
        ]

    logger.info("Creating %s agent with %s tools", mode, len(tools))
    checkpointer = await get_checkpointer()
    return create_react_agent(llm, tools=tools, prompt=prompt, checkpointer=checkpointer)
