"""CLI for AgentPolicy."""

from __future__ import annotations

import argparse
import json

from .policy import AgentPolicy


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentpolicy",
        description="Runtime policy enforcement for AI agent sessions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a policy file")
    validate_parser.add_argument("policy_file", help="Path to a YAML policy file")

    explain_parser = subparsers.add_parser("explain", help="Explain a policy file as JSON")
    explain_parser.add_argument("policy_file", help="Path to a YAML policy file")

    demo_parser = subparsers.add_parser("demo", help="Run a demo session against a policy file")
    demo_parser.add_argument("policy_file", help="Path to a YAML policy file")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "validate":
        AgentPolicy.from_yaml(args.policy_file)
        print(f"Policy valid: {args.policy_file}")
        return 0

    if args.command == "explain":
        policy = AgentPolicy.from_yaml(args.policy_file)
        print(
            json.dumps(
                {
                    "budget": policy.budget,
                    "supported_checks": ["check_tool", "check_http", "check_cost"],
                    "load_path": args.policy_file,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "demo":
        policy = AgentPolicy.from_yaml(args.policy_file)
        with policy.session(session_id="pol_demo") as session:
            for action in (
                lambda: session.check_tool("search_docs", cost=0.02),
                lambda: session.check_http("https://docs.python.org/3/", cost=0.01),
                lambda: session.check_tool("send_email"),
            ):
                try:
                    action()
                except Exception:
                    pass
            print(json.dumps(session.report(), indent=2))
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
