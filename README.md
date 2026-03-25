# AgentPolicy

### Runtime policy enforcement for AI agent sessions.

AgentPolicy is an open-source Python SDK that puts explicit runtime rules around what an agent is allowed to do. It enforces budgets, tool access, network access, and approval gates in real time, with a structured audit trail for every decision.

**One policy layer for agent behavior. Zero infrastructure to manage.**

---

## What is AgentPolicy?

Agents fail in non-deterministic ways:

- they call the wrong tool
- they hit the wrong domain
- they exceed budget
- they take an action that should require human review

AgentPolicy makes those decisions explicit and enforceable.

Each runtime action is evaluated as one of:

- `allow`
- `deny`
- `require_approval`

Every decision is recorded with the action, the reason, and the matched policy rule.

Budget is treated as a first-class policy.
AgentPolicy uses `agentbudget` under the hood for spend accounting and hard budget enforcement instead of rebuilding that layer.

---

## Quickstart

### YAML Policy (Recommended)

Define policy once. Enforce it at runtime.

```yaml
budget:
  max_spend: 5.00

tools:
  allow:
    - search_docs
    - read_file
    - send_email
  block:
    - delete_prod_db

network:
  allow:
    - docs.python.org
  block:
    - twitter.com

approval:
  require_for:
    - tool: send_email
    - cost_gt: 1.00
```

```python
from agentpolicy import AgentPolicy, ApprovalRequired

policy = AgentPolicy.from_yaml("policy.yaml")

with policy.session() as session:
    session.check_tool("search_docs", cost=0.02)
    session.check_http("https://docs.python.org/3/", cost=0.01)

    try:
        session.check_tool("send_email")
    except ApprovalRequired:
        session.check_tool("send_email", approved=True)

print(session.report())
```

### Python API

For full control, define policy directly in code.

```python
from agentpolicy import AgentPolicy

policy = AgentPolicy(
    budget="$5.00",
    allowed_tools=["search_docs", "read_file"],
    blocked_domains=["twitter.com"],
    approval_rules=[
        {"tool": "send_email"},
        {"cost_gt": 1.00},
    ],
)

with policy.session() as session:
    session.check_tool("search_docs", cost=0.02)
    session.check_http("https://docs.python.org/3/", cost=0.01)
```

---

## Install

```bash
pip install agentpolicy
```

Python 3.9+.
Installs `agentbudget` as a dependency.

For local development:

```bash
python3 -m pip install -e .[dev]
bash scripts/run_tests.sh
```

---

## Core API

| Object | Description |
|---|---|
| `AgentPolicy(...)` | Define the runtime policy envelope for an agent. |
| `AgentPolicy.from_yaml(path)` | Load a declarative policy file. |
| `AgentPolicy.from_dict(data)` | Build policy from a Python mapping. |
| `policy.session()` | Create a new `PolicySession`. |
| `session.check_tool(name, cost=...)` | Evaluate a tool execution. |
| `session.check_http(url, cost=...)` | Evaluate an outbound HTTP request. |
| `session.check_cost(cost, source=...)` | Evaluate a metered cost event such as an LLM call. |
| `session.guard_tool(...)` | Decorate a tool with policy enforcement. |
| `session.evaluate(action)` | Return a decision without enforcing it. |
| `session.enforce(action)` | Record and enforce a decision. |
| `session.report()` | Return the full structured audit report. |

---

## Policy Types

### Budget Policy

```python
policy = AgentPolicy(budget="$3.00")
```

Denies any action that would push the session over budget.

### Tool Policy

```python
policy = AgentPolicy(
    allowed_tools=["search_docs", "read_file"],
    blocked_tools=["delete_prod_db"],
)
```

Supports allowlists and explicit blocks.

### Network Policy

```python
policy = AgentPolicy(
    allowed_domains=["docs.python.org", "api.openai.com"],
    blocked_domains=["twitter.com", "facebook.com"],
)
```

Controls outbound HTTP access at the domain layer.

### Approval Policy

```python
policy = AgentPolicy(
    approval_rules=[
        {"tool": "send_email"},
        {"domain": "api.stripe.com"},
        {"cost_gt": 1.00},
    ]
)
```

Escalates sensitive actions to `ApprovalRequired`.

---

## CLI

```bash
agentpolicy validate policy.yaml
agentpolicy explain policy.yaml
agentpolicy demo policy.yaml
```

The CLI is intentionally small:

- `validate` checks that a policy file is structurally valid
- `explain` prints a simple machine-readable summary
- `demo` runs a sample session and prints the resulting report

---

## Auditability

AgentPolicy is designed to be legible under pressure.

Each decision includes:

- the action
- the decision type
- the exact reason
- the matched approval rule when escalation happens

Reports also summarize:

- decisions by type
- decisions by action category
- cost by action category
- denied tools
- denied domains
- approval-required actions

### Example Report

```python
{
    "session_id": "pol_a1b2c3d4e5f6",
    "budget": 5.0,
    "spent": 0.03,
    "remaining": 4.97,
    "decision_summary": {
        "allow": 2,
        "deny": 1,
        "require_approval": 1,
        "by_action_type": {"tool": 2, "http": 2},
    },
    "cost_summary": {
        "by_action_type": {"tool": 0.02, "http": 0.01},
    },
    "policy_hits": {
        "denied_tools": [],
        "denied_domains": ["twitter.com"],
        "approval_required": ["send_email"],
    },
    "duration_seconds": 0.14,
    "decisions": [...],
}
```

---

## Relationship to AgentBudget

`agentbudget` answers:

- how much has this agent spent?
- when should execution stop on cost?

`agentpolicy` answers:

- what can this agent do?
- what can it access?
- what requires approval?

In practice, budget is one policy dimension inside a broader runtime control layer.

The stack is:

- `agentbudget` for cost accounting and hard budget enforcement
- `agentpolicy` for the broader runtime decision layer

---

## Why it exists

Most agent tooling focuses on orchestration.
AgentPolicy focuses on control.

It is a good fit for:

- internal copilots
- research agents
- workflow automation
- production agent backends

---

## Philosophy

AgentPolicy is deliberately small.

It is not a dashboard.
It is not a hosted compliance product.
It is not an orchestration framework.

It is a runtime primitive for making agent behavior explicit and enforceable.

---

## Status

Early, but real.

The first version covers the four policy types that matter most in practice:

- spend
- tools
- network
- approval

That is enough to protect a surprising amount of real agent behavior without adding operational complexity.
