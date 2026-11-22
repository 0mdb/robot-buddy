"""Tool registry with tiers.

Each tool declares its tier (only ``read`` exists so far) and whether its
output is personal. A reply that used a personal tool comes back with
``speak: false`` so Buddy shows it on the screen only (§6.3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from .ha import HomeAssistantError, HomeAssistantReader

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    tier: Literal["read"] = "read"
    personal: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolError(Exception):
    """A tool failed in a way the model should hear about and the caller should not crash on."""


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {t.name: t for t in tools or []}

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"no tool named {name!r}")
        return await tool.handler(args)


def home_assistant_tools(ha: HomeAssistantReader) -> list[Tool]:
    domains = ", ".join(ha.domains)

    async def home_list(args: dict[str, Any]) -> Any:
        domain = args.get("domain") or None
        if domain is not None and domain not in ha.domains:
            raise ToolError(f"domain {domain!r} is not readable; readable: {domains}")
        try:
            return await ha.list_entities(domain)
        except HomeAssistantError as exc:
            raise ToolError(str(exc)) from exc

    async def home_state(args: dict[str, Any]) -> Any:
        entity_id = str(args.get("entity_id", ""))
        try:
            state = await ha.get_state(entity_id)
        except HomeAssistantError as exc:
            raise ToolError(str(exc)) from exc
        if state is None:
            raise ToolError(f"no entity {entity_id!r}; use home_list to find it")
        return state

    return [
        Tool(
            name="home_list",
            description=(
                "List Home Assistant entities and their current states. "
                f"Optionally filter by domain (one of: {domains}). "
                "Use this to find an entity_id before calling home_state."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "enum": list(ha.domains)},
                },
            },
            handler=home_list,
        ),
        Tool(
            name="home_state",
            description="Read one Home Assistant entity's current state and key attributes.",
            parameters={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "e.g. light.kitchen",
                    },
                },
                "required": ["entity_id"],
            },
            handler=home_state,
        ),
    ]
