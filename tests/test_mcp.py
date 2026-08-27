"""MCP adapter tests: read-only structured tools and composite context."""
import json

import pytest
import test_client as tc

from uptime_kuma import mcp_server


@pytest.fixture()
def fake_client(monkeypatch):
    c, _ = tc.make_scripted()
    monkeypatch.setattr(mcp_server, "create_client", lambda: c)
    return c


def test_health_tool_returns_structured_payload(fake_client):
    result = mcp_server.health()
    assert result["ok"] is True
    assert result["service"] == "uptime-kuma"


def test_list_monitors_tool_is_json_safe(fake_client):
    result = mcp_server.list_monitors()
    assert [r["id"] for r in result] == [25, 9]
    assert all("password" not in r for r in result)


def test_find_monitors_tool_filters(fake_client):
    result = mcp_server.find_monitors("SJ2")
    assert len(result) == 1 and result[0]["id"] == 25


def test_heartbeats_tool_accepts_monitor_id(fake_client):
    result = mcp_server.get_heartbeats(monitor_id=25)
    assert len(result) == 2
    assert result[-1]["label"] == "down"


def test_notifications_tool_redacts_nested_config(fake_client):
    result = mcp_server.list_notifications()
    assert "s3cret" not in json.dumps(result)


def test_incident_context_composite(fake_client):
    result = mcp_server.incident_context("mswest1 - SJ2")
    assert result["state"] == "outage"
    assert result["is_real_outage"] is True
    assert result["notifications"][0]["name"] == "hermes-alerts"
    assert "s3cret" not in json.dumps(result)


def test_no_mutating_tools_are_exposed():
    assert not hasattr(mcp_server, "pause_monitor")
    assert not hasattr(mcp_server, "delete_monitor")


# --------------------------------------------------------------- resource leak
#
# A long-running stdio MCP server previously created a fresh KumaClient per
# tool call and never closed it. Each abandoned client kept a Socket.IO
# background thread and socket FD alive, and python-socketio's default
# reconnection_attempts=0 means *infinite* retries, so every leaked client
# also retried forever. Over ~1.5 days this reached 1207 threads / 924 FDs
# and pinned a CPU core.


class _CountingClient:
    """Stands in for KumaClient, recording construction and close()."""

    created = 0
    closed = 0

    def __init__(self):
        type(self).created += 1
        self.is_closed = False

    def close(self):
        type(self).closed += 1
        self.is_closed = True

    def health(self):
        return {"ok": True, "authenticated": True, "url": "https://kuma.example"}

    def list_monitors(self):
        return []

    def find_monitors(self, query, limit=20):
        return []

    def all_heartbeats_flat(self):
        return []

    def list_notifications(self):
        return []

    def list_maintenance(self):
        return []

    def incident_context(self, monitor, lookback_minutes=60):
        return {}


@pytest.fixture()
def counting_client(monkeypatch):
    _CountingClient.created = 0
    _CountingClient.closed = 0
    monkeypatch.setattr(mcp_server, "KumaClient", _CountingClient)
    mcp_server.reset_client_for_tests()
    yield _CountingClient
    mcp_server.reset_client_for_tests()


def test_repeated_tool_calls_do_not_leak_clients(counting_client):
    """Many calls must not create an unbounded number of transports."""
    for _ in range(25):
        mcp_server.health()
        mcp_server.list_monitors()
        mcp_server.list_notifications()

    assert counting_client.created == 1, (
        f"expected a single reused client, got {counting_client.created}; "
        "each extra client leaks a socket FD and reconnect thread"
    )


def test_failed_call_closes_client_instead_of_abandoning_it(counting_client, monkeypatch):
    """A failing call must release its transport, not strand it reconnecting."""

    def boom(self):
        raise RuntimeError("kuma unreachable")

    monkeypatch.setattr(_CountingClient, "list_monitors", boom)

    with pytest.raises(RuntimeError):
        mcp_server.list_monitors()

    assert counting_client.closed == 1, (
        "a client whose call failed must be closed; otherwise it keeps "
        "retrying forever in the background"
    )
