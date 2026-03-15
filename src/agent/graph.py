from typing import Any, Dict, List, Annotated
import operator
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
import json

from config.settings import config
from src.agent.tools import retrieve_papers

# Define the State graph
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    intermediate_steps: Annotated[List[tuple[Any, str]], operator.add]
    current_plan: str
    documents: List[str]

# Setup tools and LLM
tools = [retrieve_papers]
tool_node = ToolNode(tools)

llm = ChatOpenAI(
    openai_api_base=config.OPENAI_API_BASE,
    openai_api_key=config.OPENAI_API_KEY,
    model_name=config.LLM_MODEL, # local or openai compatible name
    temperature=0.1
)

model_with_tools = llm.bind_tools(tools)

def should_continue(state: AgentState):
    """Determine whether we need to retrieve more info or end."""
    last_message = state["messages"][-1]
    # If the response has a tool call, route to tools
    if last_message.tool_calls:
        return "tools"
    # Otherwise, it's done
    return "end"

def call_model(state: AgentState):
    """Execution of the LLM given the current state"""
    messages = state["messages"]
    system_prompt = """You are an expert Research AI Assistant connecting researchers to parsed papers using a Vector DB.
    First, use tools like paper_retriever to find information about the queries.
    Then, synthesize the answers clearly and accurately citing the sources extracted from the papers.
    """
    
    # We prefix a system message implicitly
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("placeholder", "{messages}"),
    ])
    
    chain = prompt | model_with_tools
    response = chain.invoke({"messages": messages})
    return {"messages": [response]}


# Build the Graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

# Add edges connecting nodes
workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "end": END
    }
)
workflow.add_edge("tools", "agent")

# Compile app
app = workflow.compile()
