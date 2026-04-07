from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph


def _static_profile_node(state: dict[str, Any]) -> dict[str, Any]:
    return state


def _dynamic_profile_node(state: dict[str, Any]) -> dict[str, Any]:
    return state


def _final_decision_node(state: dict[str, Any]) -> dict[str, Any]:
    decision = state.get("decision_record") or {}
    error_type = state.get("error_type")
    low_conf = False
    if isinstance(decision, dict):
        low_conf = bool(decision.get("low_confidence"))
    return {
        **state,
        "route": "fallback" if error_type or low_conf else "formal",
    }


def _formal_output_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "route": "formal",
    }


def _fallback_output_node(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "route": "fallback",
    }


def _route_after_final(state: dict[str, Any]) -> str:
    return state.get("route", "fallback")


def build_graph():
    workflow = StateGraph(dict)
    workflow.add_node("static_profile", _static_profile_node)
    workflow.add_node("dynamic_profile", _dynamic_profile_node)
    workflow.add_node("final_decision", _final_decision_node)
    workflow.add_node("formal_output", _formal_output_node)
    workflow.add_node("fallback_output", _fallback_output_node)
    workflow.set_entry_point("static_profile")
    workflow.add_edge("static_profile", "dynamic_profile")
    workflow.add_edge("dynamic_profile", "final_decision")
    workflow.add_conditional_edges(
        "final_decision",
        _route_after_final,
        {
            "formal": "formal_output",
            "fallback": "fallback_output",
        },
    )
    workflow.add_edge("formal_output", END)
    workflow.add_edge("fallback_output", END)
    return workflow.compile()
