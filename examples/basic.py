from pathlib import Path

from agentpolicy import AgentPolicy, ApprovalRequired, PolicyDenied


policy = AgentPolicy.from_yaml(Path(__file__).with_name("policy.yaml"))


with policy.session() as session:
    session.check_tool("search_docs", cost=0.02)
    session.check_http("https://docs.python.org/3/", cost=0.01)

    @session.guard_tool("read_file")
    def read_file(path: str):
        return f"reading {path}"

    read_file("README.md")

    try:
        session.check_http("https://twitter.com")
    except PolicyDenied:
        pass

    try:
        session.check_tool("send_email")
    except ApprovalRequired:
        session.check_tool("send_email", approved=True)

    print(session.report())
