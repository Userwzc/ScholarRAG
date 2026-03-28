from langchain_core.tools import BaseTool  # pyright: ignore[reportMissingImports]

from src.agent.tools import get_page_context, search_papers, search_visuals

AGENT_TOOLS: list[BaseTool] = [
    search_papers,
    search_visuals,
    get_page_context,
]
TOOL_REGISTRY: dict[str, BaseTool] = {tool.name: tool for tool in AGENT_TOOLS}
