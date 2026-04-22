"""MCP (Model Context Protocol) server for robot-buddy.

Exposes the robot's capabilities as MCP tools/resources/prompts to external
LLM consumers (networked local model for hybrid tool-use; cloud Claude for
full scene orchestration). All tool calls route through the existing
PlanValidator + tick-loop safety stack.

See docs/TODO.md and the plan at
.claude/plans/let-s-brainstorm-an-mcp-composed-quill.md for phased scope.

Phase 0: scaffold with get_state tool, audit log, /ws/mcp stream.
"""

from supervisor.mcp.audit import McpAuditBroadcaster, McpAuditEntry
from supervisor.mcp.server import build_mcp_server, mcp_lifespan

__all__ = [
    "McpAuditBroadcaster",
    "McpAuditEntry",
    "build_mcp_server",
    "mcp_lifespan",
]
