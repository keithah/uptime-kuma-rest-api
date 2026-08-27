"""Read-only MCP adapter for incident investigation."""

import threading

from mcp.server.mcpserver import MCPServer

from .kuma_client import KumaClient

mcp = MCPServer("uptime-kuma")

# A stdio MCP server is a long-lived process: it is spawned once and then
# serves tool calls for days. Creating a KumaClient per call leaked one
# Socket.IO background thread and socket FD every time, and because
# python-socketio defaults to reconnection_attempts=0 (infinite), each
# abandoned client also retried forever. Observed in production after ~1.5
# days: 1207 threads, 924 open FDs, one CPU core pinned at ~58%.
#
# Instead keep a single client for the process lifetime and reuse it. On
# failure, close it and drop the reference so the next call reconnects from
# a clean state rather than stranding a retrying transport.
_client: KumaClient | None = None
_client_lock = threading.Lock()
# python-socketio's client object and its callback bookkeeping are not safe for
# overlapping application-level calls. Serialize the long-lived MCP adapter's
# calls so a second tool cannot race a reconnect or close on the shared client.
_call_lock = threading.RLock()


def _discard_client_locked() -> None:
    """Close and drop the cached client. Caller must hold _client_lock."""
    global _client
    doomed, _client = _client, None
    if doomed is None:
        return
    try:
        doomed.close()
    except Exception:
        # Teardown is best-effort: a transport that is already broken must
        # not mask the original error or block the next reconnect.
        pass


def create_client() -> KumaClient:
    """Return the process-wide client, creating it on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = KumaClient()
        return _client


def reset_client_for_tests() -> None:
    """Close and clear the cached client (test hook, also safe at shutdown)."""
    with _call_lock:
        with _client_lock:
            _discard_client_locked()


def _call(method: str, *args, **kwargs):
    """Invoke a client method, recycling the client if the call fails.

    Without this, a failed call left the cached client in a half-open state
    that reconnected in the background indefinitely.
    """
    with _call_lock:
        client = create_client()
        try:
            return getattr(client, method)(*args, **kwargs)
        except Exception:
            with _client_lock:
                # Only discard the client we actually used; a concurrent call
                # cannot replace it while _call_lock is held.
                if _client is client:
                    _discard_client_locked()
            raise


def health() -> dict:
    result = _call("health")
    return {"service": "uptime-kuma", **result}


def list_monitors() -> list[dict]:
    return _call("list_monitors")


def find_monitors(query: str, limit: int = 20) -> list[dict]:
    return _call("find_monitors", query, limit=limit)


def get_heartbeats(monitor_id: int | None = None) -> list[dict]:
    beats = _call("all_heartbeats_flat")
    return [b for b in beats if monitor_id is None or b["monitor_id"] == monitor_id]


def list_notifications() -> list[dict]:
    return _call("list_notifications")


def list_maintenance() -> list[dict]:
    return _call("list_maintenance")


def incident_context(monitor: str, lookback_minutes: int = 60) -> dict:
    return _call("incident_context", monitor, lookback_minutes=lookback_minutes)


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

    try:
        asyncio.run(mcp.run_stdio_async())
    finally:
        reset_client_for_tests()


if __name__ == "__main__":
    main()
