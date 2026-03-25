"""Policy session runtime."""

from __future__ import annotations

import functools
import time
from typing import Any, Optional
from urllib.parse import urlparse

from agentbudget import AgentBudget, BudgetExhausted

from .exceptions import ApprovalRequired, PolicyDenied
from .types import Action, ActionType, Decision, DecisionType, generate_session_id


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _format_rule(rule: dict[str, Any]) -> str:
    parts = []
    if "action_type" in rule:
        parts.append(f"action_type={rule['action_type']}")
    if "tool" in rule:
        parts.append(f"tool={rule['tool']}")
    if "domain" in rule:
        parts.append(f"domain={rule['domain']}")
    if "source" in rule:
        parts.append(f"source={rule['source']}")
    if "cost_gt" in rule:
        parts.append(f"cost_gt={rule['cost_gt']}")
    return ", ".join(parts) or "custom rule"


class PolicySession:
    """Evaluates and enforces policy decisions for a single agent run."""

    def __init__(
        self,
        budget: float,
        allowed_tools: Optional[set[str]] = None,
        blocked_tools: Optional[set[str]] = None,
        allowed_domains: Optional[set[str]] = None,
        blocked_domains: Optional[set[str]] = None,
        approval_rules: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ):
        self._budget = budget
        self._allowed_tools = allowed_tools
        self._blocked_tools = blocked_tools
        self._allowed_domains = allowed_domains
        self._blocked_domains = blocked_domains
        self._approval_rules = list(approval_rules or [])
        self._session_id = session_id or generate_session_id()
        self._spent = 0.0
        self._decisions: list[Decision] = []
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._budget_runtime = AgentBudget(self._budget) if self._budget > 0 else None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def spent(self) -> float:
        if self._budget_runtime is not None:
            session = self._budget_runtime_session()
            if session is not None:
                return session.spent
        return self._spent

    @property
    def remaining(self) -> float:
        if self._budget_runtime is not None:
            session = self._budget_runtime_session()
            if session is not None:
                return session.remaining
        return max(self._budget - self._spent, 0.0)

    @property
    def decisions(self) -> list[Decision]:
        return list(self._decisions)

    def __enter__(self) -> "PolicySession":
        self._start_time = time.time()
        if self._budget_runtime is not None:
            self._budget_runtime_session().__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._end_time = time.time()
        if self._budget_runtime is not None:
            self._budget_runtime_session().__exit__(exc_type, exc_val, exc_tb)

    def _budget_runtime_session(self):
        if self._budget_runtime is None:
            return None
        if not hasattr(self, "_budget_session"):
            self._budget_session = self._budget_runtime.session(
                session_id=f"{self._session_id}_budget"
            )
        return self._budget_session

    def _matches_rule(self, action: Action, rule: dict[str, Any]) -> bool:
        if "action_type" in rule and rule["action_type"] != action.action_type.value:
            return False
        if "tool" in rule and rule["tool"] != action.tool_name:
            return False
        if "domain" in rule and rule["domain"] != action.domain:
            return False
        if "source" in rule and rule["source"] != action.source:
            return False
        if "cost_gt" in rule and not (action.cost > float(rule["cost_gt"])):
            return False
        return True

    def evaluate(self, action: Action, approved: bool = False) -> Decision:
        """Evaluate an action against the configured policy."""
        if action.action_type == ActionType.TOOL and action.tool_name is not None:
            if self._blocked_tools and action.tool_name in self._blocked_tools:
                return Decision(
                    DecisionType.DENY,
                    f"Tool {action.tool_name!r} denied by tools.block policy",
                    action,
                )
            if self._allowed_tools is not None and action.tool_name not in self._allowed_tools:
                return Decision(
                    DecisionType.DENY,
                    f"Tool {action.tool_name!r} denied because it is not in tools.allow",
                    action,
                )

        if action.action_type == ActionType.HTTP and action.domain is not None:
            if self._blocked_domains and action.domain in self._blocked_domains:
                return Decision(
                    DecisionType.DENY,
                    f"Domain {action.domain!r} denied by network.block policy",
                    action,
                )
            if self._allowed_domains is not None and action.domain not in self._allowed_domains:
                return Decision(
                    DecisionType.DENY,
                    f"Domain {action.domain!r} denied because it is not in network.allow",
                    action,
                )

        current_spent = self.spent
        if self._budget and (current_spent + action.cost) > self._budget:
            return Decision(
                DecisionType.DENY,
                f"Budget exceeded: ${current_spent + action.cost:.4f} would exceed ${self._budget:.2f}",
                action,
            )

        if not approved:
            for index, rule in enumerate(self._approval_rules, start=1):
                if self._matches_rule(action, rule):
                    return Decision(
                        DecisionType.REQUIRE_APPROVAL,
                        f"Action requires approval by rule #{index}: {_format_rule(rule)}",
                        action,
                    )

        return Decision(DecisionType.ALLOW, "Action allowed", action)

    def enforce(self, action: Action, approved: bool = False) -> Decision:
        """Evaluate an action, record the decision, and raise on deny/escalate."""
        decision = self.evaluate(action, approved=approved)
        self._decisions.append(decision)
        if decision.decision_type == DecisionType.ALLOW:
            if action.cost > 0:
                if self._budget_runtime is not None:
                    try:
                        self._budget_runtime_session().track(
                            None,
                            cost=action.cost,
                            tool_name=f"policy:{action.action_type.value}",
                        )
                    except BudgetExhausted:
                        self._decisions[-1] = Decision(
                            DecisionType.DENY,
                            f"Budget exceeded: ${self.spent + action.cost:.4f} would exceed ${self._budget:.2f}",
                            action,
                        )
                        raise PolicyDenied(self._decisions[-1].reason)
                else:
                    self._spent += action.cost
            return decision
        if decision.decision_type == DecisionType.DENY:
            raise PolicyDenied(decision.reason)
        raise ApprovalRequired(decision.reason)

    def check_tool(
        self,
        tool_name: str,
        cost: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
        approved: bool = False,
    ) -> Decision:
        """Evaluate a tool execution."""
        action = Action(
            action_type=ActionType.TOOL,
            tool_name=tool_name,
            cost=cost,
            metadata=metadata,
        )
        return self.enforce(action, approved=approved)

    def check_http(
        self,
        url: str,
        cost: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
        approved: bool = False,
    ) -> Decision:
        """Evaluate an outbound HTTP request."""
        action = Action(
            action_type=ActionType.HTTP,
            url=url,
            domain=_extract_domain(url),
            cost=cost,
            metadata=metadata,
        )
        return self.enforce(action, approved=approved)

    def check_cost(
        self,
        cost: float,
        source: str = "llm",
        metadata: Optional[dict[str, Any]] = None,
        approved: bool = False,
    ) -> Decision:
        """Evaluate a metered cost event."""
        action = Action(
            action_type=ActionType.COST,
            source=source,
            cost=cost,
            metadata=metadata,
        )
        return self.enforce(action, approved=approved)

    def guard_tool(
        self,
        tool_name: Optional[str] = None,
        cost: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
        approved: bool = False,
    ):
        """Decorator that evaluates policy before executing a tool."""
        def decorator(func):
            name = tool_name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                self.check_tool(
                    name,
                    cost=cost,
                    metadata=metadata,
                    approved=approved,
                )
                return func(*args, **kwargs)

            return wrapper

        return decorator

    def report(self) -> dict[str, Any]:
        """Return a structured audit report for the session."""
        duration = None
        if self._start_time is not None:
            end = self._end_time or time.time()
            duration = round(end - self._start_time, 2)

        allow_count = sum(1 for d in self._decisions if d.decision_type == DecisionType.ALLOW)
        deny_count = sum(1 for d in self._decisions if d.decision_type == DecisionType.DENY)
        approval_count = sum(
            1 for d in self._decisions if d.decision_type == DecisionType.REQUIRE_APPROVAL
        )
        by_action_type: dict[str, int] = {}
        denied_tools: list[str] = []
        denied_domains: list[str] = []
        approval_actions: list[str] = []
        cost_by_action_type: dict[str, float] = {}

        for decision in self._decisions:
            action_type = decision.action.action_type.value
            by_action_type[action_type] = by_action_type.get(action_type, 0) + 1
            cost_by_action_type[action_type] = (
                cost_by_action_type.get(action_type, 0.0) + decision.action.cost
            )

            if decision.decision_type == DecisionType.DENY:
                if decision.action.tool_name is not None:
                    denied_tools.append(decision.action.tool_name)
                if decision.action.domain is not None:
                    denied_domains.append(decision.action.domain)

            if decision.decision_type == DecisionType.REQUIRE_APPROVAL:
                if decision.action.tool_name is not None:
                    approval_actions.append(decision.action.tool_name)
                elif decision.action.domain is not None:
                    approval_actions.append(decision.action.domain)
                else:
                    approval_actions.append(action_type)

        return {
            "session_id": self._session_id,
            "budget": self._budget,
            "spent": round(self.spent, 6),
            "remaining": round(self.remaining, 6),
            "decision_summary": {
                "allow": allow_count,
                "deny": deny_count,
                "require_approval": approval_count,
                "by_action_type": by_action_type,
            },
            "cost_summary": {
                "by_action_type": {
                    key: round(value, 6) for key, value in cost_by_action_type.items()
                },
            },
            "policy_hits": {
                "denied_tools": denied_tools,
                "denied_domains": denied_domains,
                "approval_required": approval_actions,
            },
            "duration_seconds": duration,
            "decisions": [decision.to_dict() for decision in self._decisions],
        }
