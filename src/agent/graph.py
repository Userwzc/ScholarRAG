from typing import Annotated, List

import operator
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from config.settings import config
from src.agent.tools import retrieve_papers

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """Minimal state carried through the LangGraph execution."""

    messages: Annotated[List[BaseMessage], operator.add]


# ---------------------------------------------------------------------------
# LLM & tools
# ---------------------------------------------------------------------------

tools = [retrieve_papers]
tool_node = ToolNode(tools)

llm = ChatOpenAI(
    openai_api_base=config.OPENAI_API_BASE,
    openai_api_key=config.OPENAI_API_KEY,
    model_name=config.LLM_MODEL,
    temperature=0.1,
)

model_with_tools = llm.bind_tools(tools)

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Research AI Assistant.  Your knowledge base consists of \
academic papers stored in a vector database, which you access through the \
paper_retriever tool.

## Retrieval rules
- Always call paper_retriever at least once before answering any question about \
paper content, methodology, results, figures, tables, equations, or authors.
- For multi-part questions, call paper_retriever multiple times with focused \
sub-queries — one call per distinct aspect — rather than a single broad query.
- If an initial retrieval returns low-confidence chunks (Score < 0.35), try a \
rephrased or narrower query before concluding the information is absent.

## Answer rules
- Base your answer strictly on the retrieved chunks.  Do not invent facts, \
equations, or citations that are not present in the retrieved text.
- If the retrieved chunks do not contain enough information to answer the \
question, state this clearly rather than guessing.
- For every factual claim, cite the source using the format: \
(Author(s), Page N) or (PDF: <pdf_name>, Page N) when page information is \
available in the chunk metadata.
- Prefer precise, concise language.  Use bullet points or numbered lists when \
presenting multiple findings or steps.

## Scope
- If the user asks a question that is entirely unrelated to research papers \
(e.g. general coding help, casual conversation), politely note that you are \
specialised for academic paper Q&A and attempt to help with what is in the \
database if applicable.
"""


def call_model(state: AgentState) -> dict:
    """Invoke the LLM with the current message history, prepending the system prompt."""
    messages = [SystemMessage(content=_SYSTEM_PROMPT)] + state["messages"]
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """Route to 'tools' if the last AI message has tool calls, else end."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "end": END},
)
workflow.add_edge("tools", "agent")

# Compile with a recursion limit to prevent runaway tool loops.
# config.AGENT_MAX_ITERATIONS controls how many node-visits are allowed; each
# round-trip (agent → tools → agent) counts as 2 iterations, so the effective
# maximum number of tool calls is roughly AGENT_MAX_ITERATIONS // 2.
app = workflow.compile(recursion_limit=config.AGENT_MAX_ITERATIONS)
