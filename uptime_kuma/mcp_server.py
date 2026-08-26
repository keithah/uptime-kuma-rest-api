"""Read-only MCP adapter for incident investigation."""
from typing import Any

from mcp.server.mcpserver import MCPServer

from .kuma_client import KumaClient

mcp = MCPServer("uptime-kuma")


def create_client() -> KumaClient:
    return KumaClient()


def health() -> dict:
    result = create_client().health()
    return {"service": "uptime-kuma", **result}


def list_monitors() -> list[dict]:
    return create_client().list_monitors()


def find_monitors(query: str, limit: int = 20) -> list[dict]:
    return create_client().find_monitors(query, limit=limit)


def get_heartbeats(monitor_id: int | None = None) -> list[dict]:
    client = create_client()
    beats = client.all_heartbeats_flat()
    return [b for b in beats if monitor_id is None or b["monitor_id"] == monitor_id]


def list_notifications() -> list[dict]:
    return create_client().list_notifications()


def list_maintenance() -> list[dict]:
    return create_client().list_maintenance()


def incident_context(monitor: str, lookback_minutes: int = 60) -> dict:
    return create_client().incident_context(monitor, lookback_minutes=lookback_minutes)


# Register only read-only tools. Mutation methods intentionally have no decorators.
mcp.tool()(health)
mcp.tool()(list_monitors)
mcp.tool()(find_monitors)
mcp.tool()(get_heartbeats)
mcp.tool()(list_notifications)
mcp.tool()(list_maintenance)
mcp.tool(name="kuma_incident_context")(incident_context)


def main() -> None:
    import asyncio
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
