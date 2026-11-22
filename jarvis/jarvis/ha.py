"""Home Assistant, read tier only (docs/screen-ui-and-admin.md §6.4).

This client has GET methods and nothing else, so the read tier cannot change
anything in the house whatever the model asks for. The reversible tier (lights,
thermostat, media, with a confirm tap) comes later through HA's MCP server and
its own allow-list.
"""

from __future__ import annotations

from typing import Any

import httpx

# Attributes worth handing the model; the rest (icons, supported_features, ...)
# is noise that costs context.
_KEEP_ATTRS = (
    "friendly_name",
    "unit_of_measurement",
    "device_class",
    "brightness",
    "current_temperature",
    "temperature",
    "hvac_action",
    "current_position",
    "media_title",
    "media_artist",
    "volume_level",
    "humidity",
)


class HomeAssistantError(Exception):
    pass


class HomeAssistantReader:
    def __init__(
        self, url: str, token: str, domains: tuple[str, ...], timeout_s: float = 5.0
    ) -> None:
        self.domains = domains
        self._client = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def allowed(self, entity_id: str) -> bool:
        domain, dot, _ = entity_id.partition(".")
        return bool(dot) and domain in self.domains

    async def _get(self, path: str) -> Any:
        try:
            resp = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Home Assistant unreachable: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise HomeAssistantError(f"Home Assistant returned {resp.status_code}")
        return resp.json()

    @staticmethod
    def _slim(state: dict[str, Any]) -> dict[str, Any]:
        attrs = state.get("attributes") or {}
        return {
            "entity_id": state.get("entity_id"),
            "state": state.get("state"),
            **{k: attrs[k] for k in _KEEP_ATTRS if k in attrs},
            "last_changed": state.get("last_changed"),
        }

    async def list_entities(
        self, domain: str | None = None, limit: int = 60
    ) -> list[dict[str, Any]]:
        states = await self._get("/api/states") or []
        out = []
        for st in states:
            eid = st.get("entity_id", "")
            if not self.allowed(eid):
                continue
            if domain and not eid.startswith(f"{domain}."):
                continue
            out.append(self._slim(st))
            if len(out) >= limit:
                break
        return out

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        if not self.allowed(entity_id):
            raise HomeAssistantError(f"{entity_id} is not in the readable domains")
        st = await self._get(f"/api/states/{entity_id}")
        return self._slim(st) if st else None
