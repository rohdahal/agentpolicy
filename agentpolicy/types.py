"""Core data types for AgentPolicy."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ActionType(Enum):
    """Supported runtime action categories."""

    TOOL = "tool"
    HTTP = "http"
    COST = "cost"


class DecisionType(Enum):
    """Possible policy decisions."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"pol_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class Action:
    """A single action emitted by an agent runtime."""

    action_type: ActionType
    cost: float = 0.0
    tool_name: Optional[str] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    source: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "action_type": self.action_type.value,
            "cost": self.cost,
            "timestamp": self.timestamp,
        }
        if self.tool_name is not None:
            data["tool_name"] = self.tool_name
        if self.url is not None:
            data["url"] = self.url
        if self.domain is not None:
            data["domain"] = self.domain
        if self.source is not None:
            data["source"] = self.source
        if self.metadata is not None:
            data["metadata"] = self.metadata
        return data


@dataclass(frozen=True)
class Decision:
    """The policy engine's decision for an action."""

    decision_type: DecisionType
    reason: str
    action: Action
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_type": self.decision_type.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "action": self.action.to_dict(),
        }
