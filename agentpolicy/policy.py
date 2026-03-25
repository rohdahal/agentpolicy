"""Top-level policy configuration and factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .exceptions import InvalidPolicy
from .session import PolicySession


def parse_money(value: str | float | int) -> float:
    """Parse a dollar amount into a float."""
    if isinstance(value, (int, float)):
        if value < 0:
            raise InvalidPolicy(f"Budget must be non-negative, got {value!r}")
        return float(value)

    if isinstance(value, str):
        cleaned = value.strip().lstrip("$").strip()
        try:
            amount = float(cleaned)
        except ValueError as exc:
            raise InvalidPolicy(f"Invalid money value: {value!r}") from exc
        if amount < 0:
            raise InvalidPolicy(f"Budget must be non-negative, got {value!r}")
        return amount

    raise InvalidPolicy(f"Invalid money value: {value!r}")


def _normalize_names(values: Optional[Iterable[str]]) -> Optional[set[str]]:
    if values is None:
        return None
    normalized = {value.strip() for value in values if value and value.strip()}
    return normalized or set()


def _get_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidPolicy(f"Policy section {key!r} must be a mapping")
    return value


class AgentPolicy:
    """Runtime policy envelope for an agent session."""

    def __init__(
        self,
        budget: str | float | int = 0.0,
        allowed_tools: Optional[Iterable[str]] = None,
        blocked_tools: Optional[Iterable[str]] = None,
        allowed_domains: Optional[Iterable[str]] = None,
        blocked_domains: Optional[Iterable[str]] = None,
        approval_rules: Optional[list[dict[str, Any]]] = None,
    ):
        self._budget = parse_money(budget)
        self._allowed_tools = _normalize_names(allowed_tools)
        self._blocked_tools = _normalize_names(blocked_tools)
        self._allowed_domains = _normalize_names(allowed_domains)
        self._blocked_domains = _normalize_names(blocked_domains)
        self._approval_rules = list(approval_rules or [])

        if (
            self._allowed_tools is not None
            and self._blocked_tools is not None
            and self._allowed_tools.intersection(self._blocked_tools)
        ):
            raise InvalidPolicy("Tool cannot be both allowed and blocked")

        if (
            self._allowed_domains is not None
            and self._blocked_domains is not None
            and self._allowed_domains.intersection(self._blocked_domains)
        ):
            raise InvalidPolicy("Domain cannot be both allowed and blocked")

    @property
    def budget(self) -> float:
        return self._budget

    def session(self, session_id: Optional[str] = None) -> PolicySession:
        """Create a new policy session."""
        return PolicySession(
            budget=self._budget,
            allowed_tools=self._allowed_tools,
            blocked_tools=self._blocked_tools,
            allowed_domains=self._allowed_domains,
            blocked_domains=self._blocked_domains,
            approval_rules=self._approval_rules,
            session_id=session_id,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentPolicy":
        """Build a policy from a declarative mapping."""
        budget_block = _get_mapping(data, "budget")
        tools_block = _get_mapping(data, "tools")
        network_block = _get_mapping(data, "network")
        approval_block = _get_mapping(data, "approval")

        approval_rules = approval_block.get("require_for")
        if approval_rules is not None and not isinstance(approval_rules, list):
            raise InvalidPolicy("Policy section 'approval.require_for' must be a list")

        return cls(
            budget=budget_block.get("max_spend", 0.0),
            allowed_tools=tools_block.get("allow"),
            blocked_tools=tools_block.get("block"),
            allowed_domains=network_block.get("allow"),
            blocked_domains=network_block.get("block"),
            approval_rules=approval_rules,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentPolicy":
        """Load a policy from YAML."""
        file_path = Path(path)
        with file_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise InvalidPolicy("Policy file must contain a top-level mapping")
        return cls.from_dict(data)
