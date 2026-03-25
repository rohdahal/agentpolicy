"""Tests for AgentPolicy."""

from pathlib import Path

import pytest

from agentpolicy import AgentPolicy, ApprovalRequired, InvalidPolicy, PolicyDenied, parse_money
from agentpolicy.types import Action, ActionType


def test_parse_money():
    assert parse_money("$5.00") == 5.0
    assert parse_money("5") == 5.0
    assert parse_money(0) == 0.0


def test_negative_money_rejected():
    with pytest.raises(InvalidPolicy):
        parse_money(-1)


def test_conflicting_tool_policy_rejected():
    with pytest.raises(InvalidPolicy):
        AgentPolicy(allowed_tools=["search_docs"], blocked_tools=["search_docs"])


def test_conflicting_domain_policy_rejected():
    with pytest.raises(InvalidPolicy):
        AgentPolicy(allowed_domains=["docs.python.org"], blocked_domains=["docs.python.org"])


def test_tool_allowlist():
    policy = AgentPolicy(allowed_tools=["search_docs"])
    with policy.session() as session:
        session.check_tool("search_docs")
        with pytest.raises(PolicyDenied):
            session.check_tool("send_email")


def test_tool_blocklist():
    policy = AgentPolicy(blocked_tools=["delete_prod_db"])
    with policy.session() as session:
        with pytest.raises(PolicyDenied):
            session.check_tool("delete_prod_db")


def test_domain_allowlist():
    policy = AgentPolicy(allowed_domains=["docs.python.org"])
    with policy.session() as session:
        session.check_http("https://docs.python.org/3/")
        with pytest.raises(PolicyDenied):
            session.check_http("https://example.com")


def test_domain_blocklist():
    policy = AgentPolicy(blocked_domains=["twitter.com"])
    with policy.session() as session:
        with pytest.raises(PolicyDenied) as exc_info:
            session.check_http("https://twitter.com/agentbudget")
        assert "network.block" in str(exc_info.value)


def test_budget_denial():
    policy = AgentPolicy(budget="$0.05")
    with policy.session() as session:
        session.check_cost(0.03)
        with pytest.raises(PolicyDenied):
            session.check_cost(0.03)


def test_approval_rule_for_tool():
    policy = AgentPolicy(approval_rules=[{"tool": "send_email"}])
    with policy.session() as session:
        with pytest.raises(ApprovalRequired) as exc_info:
            session.check_tool("send_email")
        assert "rule #1" in str(exc_info.value)
        session.check_tool("send_email", approved=True)


def test_approval_rule_for_cost():
    policy = AgentPolicy(approval_rules=[{"cost_gt": 1.0}])
    with policy.session() as session:
        with pytest.raises(ApprovalRequired):
            session.check_cost(2.0, source="llm")


def test_report_shape():
    policy = AgentPolicy(budget="$1.00", blocked_tools=["delete_prod_db"])
    with policy.session(session_id="pol_test") as session:
        session.check_tool("search_docs", cost=0.1)
        with pytest.raises(PolicyDenied):
            session.check_tool("delete_prod_db")

    report = session.report()
    assert report["session_id"] == "pol_test"
    assert report["spent"] == 0.1
    assert report["decision_summary"]["allow"] == 1
    assert report["decision_summary"]["deny"] == 1
    assert report["decision_summary"]["by_action_type"]["tool"] == 2
    assert report["cost_summary"]["by_action_type"]["tool"] == 0.1
    assert report["policy_hits"]["denied_tools"] == ["delete_prod_db"]


def test_budget_policy_tracks_multiple_allowed_actions():
    policy = AgentPolicy(budget="$1.00")
    with policy.session() as session:
        session.check_tool("search_docs", cost=0.2)
        session.check_http("https://docs.python.org/3/", cost=0.3)

    report = session.report()
    assert report["spent"] == 0.5
    assert report["remaining"] == 0.5


def test_from_yaml():
    policy = AgentPolicy.from_yaml(
        Path(__file__).resolve().parents[1] / "examples" / "policy.yaml"
    )
    with policy.session() as session:
        session.check_tool("search_docs", cost=0.01)
        with pytest.raises(PolicyDenied):
            session.check_tool("delete_prod_db")


def test_from_dict():
    policy = AgentPolicy.from_dict(
        {
            "budget": {"max_spend": 2.0},
            "tools": {"allow": ["search_docs"]},
            "network": {"block": ["twitter.com"]},
            "approval": {"require_for": [{"tool": "search_docs", "cost_gt": 1.0}]},
        }
    )
    assert policy.budget == 2.0


def test_from_yaml_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad_policy.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(InvalidPolicy):
        AgentPolicy.from_yaml(path)


def test_from_dict_rejects_invalid_section():
    with pytest.raises(InvalidPolicy):
        AgentPolicy.from_dict({"tools": ["search_docs"]})


def test_from_dict_rejects_invalid_approval_section():
    with pytest.raises(InvalidPolicy):
        AgentPolicy.from_dict({"approval": {"require_for": "send_email"}})


def test_guard_tool_decorator():
    policy = AgentPolicy(allowed_tools=["read_file"])
    with policy.session() as session:

        @session.guard_tool("read_file")
        def read_file(path):
            return path

        assert read_file("README.md") == "README.md"


def test_guard_tool_denies_before_execution():
    policy = AgentPolicy(blocked_tools=["delete_prod_db"])
    with policy.session() as session:
        called = {"value": False}

        @session.guard_tool("delete_prod_db")
        def destructive_tool():
            called["value"] = True

        with pytest.raises(PolicyDenied):
            destructive_tool()

        assert called["value"] is False


def test_report_has_policy_hits():
    policy = AgentPolicy(
        blocked_domains=["twitter.com"],
        approval_rules=[{"tool": "send_email"}],
    )
    with policy.session() as session:
        with pytest.raises(PolicyDenied):
            session.check_http("https://twitter.com")
        with pytest.raises(ApprovalRequired):
            session.check_tool("send_email")

    report = session.report()
    assert report["policy_hits"]["denied_domains"] == ["twitter.com"]
    assert report["policy_hits"]["approval_required"] == ["send_email"]


def test_evaluate_does_not_mutate_spend_or_decisions():
    policy = AgentPolicy(budget="$1.00")
    with policy.session() as session:
        decision = session.evaluate(
            Action(action_type=ActionType.COST, cost=0.25, source="llm")
        )
        assert decision.decision_type.value == "allow"
        assert session.spent == 0.0
        assert session.decisions == []
