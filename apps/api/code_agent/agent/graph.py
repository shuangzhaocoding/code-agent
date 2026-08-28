from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from code_agent.agent.checkpointer import get_checkpointer
from code_agent.agent.nodes.compress import compress_node
from code_agent.agent.nodes.model import agent_node
from code_agent.agent.nodes.prepare_context import prepare_context_node
from code_agent.agent.routing import route_after_agent, route_after_prepare
from code_agent.agent.state import AgentState


def build_agent_graph(tools: list):
    workflow = StateGraph(AgentState)
    workflow.add_node("prepare_context", prepare_context_node)
    workflow.add_node("compress", compress_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "prepare_context")
    workflow.add_conditional_edges(
        "prepare_context",
        route_after_prepare,
        {"compress": "compress", "agent": "agent"},
    )
    workflow.add_edge("compress", "agent")
    workflow.add_conditional_edges(
        "agent",
        route_after_agent,
        {"tools": "tools", "end": END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=get_checkpointer())
