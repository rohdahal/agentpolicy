"""Exceptions for AgentPolicy."""


class AgentPolicyError(Exception):
    """Base exception for AgentPolicy errors."""


class InvalidPolicy(AgentPolicyError):
    """Raised when policy configuration is invalid."""

    def __init__(self, message: str):
        super().__init__(message)


class PolicyDenied(AgentPolicyError):
    """Raised when an action is denied by policy."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ApprovalRequired(AgentPolicyError):
    """Raised when an action requires explicit approval."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
