"""CLI tests: JSON output, exit codes, redaction, destructive-op gating."""
import json

import pytest
import test_client as tc

from uptime_kuma import cli
from uptime_kuma.errors import AuthError, ConnectionError_, TimeoutError_


class FakeKuma(tc.KumaClient):  # reuse scripted behavior
    pass


@pytest.fixture()
def fake_client(monkeypatch):
    c, _ = tc.make_scripted()
    monkeypatch.setattr(cli, "create_client", lambda: c)
    return c


def run(argv):
    return cli.main(argv)


# ---------------------------------------------------------------- reads

def test_health_json_exit_0(fake_client, capsys):
    assert run(["health", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True


def test_monitors_list_json(fake_client, capsys):
    assert run(["monitors", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in rows} == {25, 9}


def test_monitors_find_json(fake_client, capsys):
    assert run(["monitors", "find", "--query", "sj2", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1 and rows[0]["id"] == 25


def test_heartbeats_json(fake_client, capsys):
    assert run(["heartbeats", "--monitor-id", "25", "--json"]) == 0
    beats = json.loads(capsys.readouterr().out)
    assert len(beats) == 2 and beats[-1]["label"] == "down"


def test_notifications_list_redacted_json(fake_client, capsys):
    assert run(["notifications", "list", "--json"]) == 0
    out = capsys.readouterr().out
    assert "s3cret" not in out
    rows = json.loads(out)
    assert rows[0]["name"] == "hermes-alerts"


def test_maintenance_list_json(fake_client, capsys):
    assert run(["maintenance", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["title"] == "nightly"


def test_incident_context_json(fake_client, capsys):
    assert run(["incident-context", "--monitor", "mswest1 - SJ2", "--json"]) == 0
    ctx = json.loads(capsys.readouterr().out)
    assert ctx["state"] == "outage"
    assert ctx["is_real_outage"] is True


# ---------------------------------------------------------------- exit codes

def test_connection_error_exit_3(monkeypatch):
    class Boom:
        def __getattr__(self, name):
            raise ConnectionError_("down")

    monkeypatch.setattr(cli, "create_client", lambda: Boom())
    assert run(["health", "--json"]) == 3


def test_auth_error_exit_4(monkeypatch):
    class Boom:
        def __getattr__(self, name):
            raise AuthError("bad creds")

    monkeypatch.setattr(cli, "create_client", lambda: Boom())
    assert run(["health", "--json"]) == 4


def test_timeout_error_exit_5(monkeypatch):
    class Boom:
        def __getattr__(self, name):
            raise TimeoutError_("slow")

    monkeypatch.setattr(cli, "create_client", lambda: Boom())
    assert run(["monitors", "list", "--json"]) == 5


def test_generic_kuma_error_exit_1(monkeypatch):
    from uptime_kuma.errors import KumaError

    class Boom:
        def __getattr__(self, name):
            raise KumaError("weird")

    monkeypatch.setattr(cli, "create_client", lambda: Boom())
    assert run(["monitors", "list", "--json"]) == 1


# ---------------------------------------------------------------- mutations

def test_pause_requires_yes(fake_client):
    assert run(["monitor", "pause", "--id", "25"]) != 0


def test_pause_with_yes_calls_event(fake_client):
    calls = []
    fake_client._transport.emits.clear()
    def spy(event, data=None, timeout=15.0):
        calls.append((event, data))
        return {"ok": True}
    fake_client._transport.emit_ack = spy
    assert run(["monitor", "pause", "--id", "25", "--yes"]) == 0
    assert ("pauseMonitor", 25) in calls


def test_bulk_control_dry_run_lists_targets_only(fake_client, capsys):
    rc = run(["bulk-control", "--name-pattern", "*SJ*", "--action", "pause", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "mswest1 - SJ2" in out
    assert all(e[0] != "pauseMonitor" for e in fake_client._transport.emits)


def test_bulk_delete_requires_explicit_yes_and_shows_targets(fake_client, capsys):
    rc = run(["bulk-control", "--name-pattern", "weekly*", "--action", "delete"])
    assert rc != 0
    assert "weekly cert" in capsys.readouterr().out


def test_bulk_update_edits_full_monitor_object_not_bare_patch(fake_client):
    emitted = []
    orig = fake_client._transport.emit_ack
    def spy(event, data=None, timeout=15.0):
        if event == "editMonitor":
            emitted.append((event, data))
            return {"ok": True}
        return orig(event, data, timeout)
    fake_client._transport.emit_ack = spy
    rc = run(["bulk-update", "--name-pattern", "*SJ2*",
              "--updates", '{"maxretries": 2}', "--yes"])
    assert rc == 0
    edits = [d for e, d in emitted if e == "editMonitor"]
    assert len(edits) == 1
    assert edits[0]["maxretries"] == 2                                # field applied
    assert edits[0]["url"] == "http://plex:3002/plex/mswest1/sj2"     # object intact
