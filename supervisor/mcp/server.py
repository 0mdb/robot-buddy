"""Build the MCP server and wire it into the supervisor's FastAPI app.

Uses FastMCP from the official `mcp` Python SDK with Streamable HTTP
transport (the current standard). Mounted at /mcp on the main FastAPI app.
Tools are closures over (tick, audit) so implementations stay in tools.py
and remain unit-testable without the MCP plumbing.

Phase 0 exposes: get_state. Tools #2 (look), #3 (get_memory, recent_events)
will register on the same FastMCP instance in follow-on tasks.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from supervisor.mcp.audit import McpAuditBroadcaster
from supervisor.mcp.tools import (
    get_memory_impl,
    get_state_impl,
    look_impl,
    recent_events_impl,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

    from supervisor.core.tick_loop import TickLoop
    from supervisor.core.worker_manager import WorkerManager

log = logging.getLogger(__name__)

# Matches the path used by the /api/personality/memory HTTP endpoint in
# supervisor/api/http_server.py so the MCP tool reads the same file the
# parent dashboard serves.
DEFAULT_MEMORY_PATH = Path("./data/personality_memory.json")


def build_mcp_server(
    tick: TickLoop,
    audit: McpAuditBroadcaster,
    workers: WorkerManager,
    *,
    name: str = "robot-buddy",
    memory_path: Path | None = None,
) -> FastMCP:
    """Construct the FastMCP server with Phase 0 tools registered."""
    # streamable_http_path="/" so the endpoint lives at the root of the
    # sub-app; mounted at /mcp on the parent this gives clients the
    # canonical /mcp endpoint rather than the doubled /mcp/mcp.
    # Disable DNS-rebinding protection: the supervisor is a LAN-only
    # service (the Pi's 192.168.55.x IP) with no browser-facing UI that
    # a drive-by attack could weaponize; the default protection rejects
    # every non-localhost Host header as 421 Misdirected Request.
    mcp = FastMCP(
        name,
        json_response=True,
        stateless_http=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
    mem_path = memory_path if memory_path is not None else DEFAULT_MEMORY_PATH

    @mcp.tool()
    async def get_state() -> dict:
        """Compact snapshot of the robot's current state — mode, mood, battery,
        faults, conversation state, recent vision + speaking status. Safe to
        call freely; read-only."""
        return await get_state_impl(tick, audit)

    @mcp.tool()
    async def get_memory(category: str | None = None) -> dict:
        """List known memory tags about this child/user, optionally filtered
        by category. Categories: name, topic, ritual, tone, preference.
        Entries come back sorted by current decayed strength (strongest
        first) so recent or frequently-reinforced memories are easy to spot.
        Read-only."""
        return await get_memory_impl(mem_path, category, audit)

    @mcp.tool()
    async def recent_events(pattern: str | None = None, n: int = 10) -> dict:
        """Return recent high-level planner events (button presses, touches,
        ball detections, obstacle state, faults, mode changes). Optional
        case-insensitive substring filter on event type. n is clamped to
        [1, 50]. Read-only."""
        return await recent_events_impl(tick, pattern, n, audit)

    @mcp.tool()
    async def look(hint: str | None = None) -> list[Any]:
        """Return the robot's current camera view — a fresh JPEG (320x240)
        plus ball-detection metadata (ball visible, bearing, frame age).
        Use this when the child references something visual ("look at
        this!", "see my drawing?", "what color is it?"). `hint` is optional
        free text describing what you want to notice; it's logged but not
        interpreted.

        Returns an MCP content list: an image block (when parental memory
        consent is on and the frame is fresh) plus a JSON metadata text
        block explaining what's in the frame. When consent is off, only
        the metadata is returned — no image bytes leave the robot."""
        return await look_impl(tick, workers, hint, audit)

    return mcp


@asynccontextmanager
async def mcp_lifespan(app: FastAPI, mcp: FastMCP) -> AsyncIterator[None]:
    """Lifespan context that runs the MCP session manager alongside FastAPI.

    Use via FastAPI(lifespan=partial(mcp_lifespan, mcp=mcp_server)) or inline
    in create_app. Streamable HTTP needs the session manager running while the
    app is serving.
    """
    async with mcp.session_manager.run():
        log.info("MCP session manager started")
        try:
            yield
        finally:
            log.info("MCP session manager stopping")
