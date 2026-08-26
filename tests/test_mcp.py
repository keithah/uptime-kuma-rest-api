"""MCP adapter tests: read-only structured tools and composite context."""
import json

import pytest

from uptime_kuma import mcp_server
import test_client as tc


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
