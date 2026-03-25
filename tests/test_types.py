"""Tests for AgentPolicy types."""

from agentpolicy.types import Action, ActionType, Decision, DecisionType, generate_session_id


def test_generate_session_id_format():
    session_id = generate_session_id()
    assert session_id.startswith("pol_")
    assert len(session_id) == 16


def test_action_to_dict():
    action = Action(
        action_type=ActionType.HTTP,
        cost=0.25,
        url="https://docs.python.org/3/",
        domain="docs.python.org",
        metadata={"kind": "docs"},
    )
    data = action.to_dict()
    assert data["action_type"] == "http"
    assert data["cost"] == 0.25
    assert data["domain"] == "docs.python.org"


def test_decision_to_dict():
    action = Action(action_type=ActionType.TOOL, tool_name="search_docs")
    decision = Decision(
        decision_type=DecisionType.ALLOW,
        reason="Action allowed",
        action=action,
    )
    data = decision.to_dict()
    assert data["decision_type"] == "allow"
    assert data["reason"] == "Action allowed"
    assert data["action"]["tool_name"] == "search_docs"
