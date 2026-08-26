"""Tests for KumaClient against a fake transport (offline, no real socket)."""
import pytest

from uptime_kuma.config import Config
from uptime_kuma.errors import AuthError, ConnectionError_, TimeoutError_, KumaError
from uptime_kuma.transport import AckTransport
from uptime_kuma.kuma_client import KumaClient


def make_cfg(**kw):
    return Config(url="https://kuma.test", username="u", password="p", **kw)


class FakeTransport(AckTransport):
    """Scriptable fake: handlers map event -> ack value or callable."""

    def __init__(self, script=None, fail_connect=False, drop_acks_for=()):
        self.script = script or {}
        self.fail_connect = fail_connect
        self.drop_acks_for = set(drop_acks_for)
        self.connected = False
        self.emits = []
        self.push_handlers = {}

    def connect(self):
        if self.fail_connect:
            raise OSError("refused")
        self.connected = True

    def close(self):
        self.connected = False

    def emit_ack(self, event, data=None, timeout=15.0):
        self.emits.append((event, data))
        if event in self.drop_acks_for:
            raise TimeoutError_(f"no ack for {event}")
        handler = self.script.get(event)
        if handler is None:
            raise TimeoutError_(f"no script for {event}")
        return handler(data) if callable(handler) else handler

    def on(self, event, handler):
        self.push_handlers.setdefault(event, []).append(handler)

    def fire_push(self, event, *payload):
        for h in self.push_handlers.get(event, []):
            h(*payload)


def login_ok(data):
    assert data["username"] == "u"
    return {"ok": True, "token": "jwt123"}


MONITORS = {
    "25": {"id": 25, "name": "mswest1 - SJ2", "type": "http",
           "url": "http://plex:3002/plex/mswest1/sj2", "interval": 60,
           "active": True},
    "9": {"id": 9, "name": "weekly cert", "type": "http",
          "url": "https://cert.example/", "interval": 2073600,
          "active": True},
}
HEARTBEATS = {
    "25": [
        {"monitorID": 25, "status": 1, "time": "2026-08-26 12:00:00", "msg": "OK", "ping": 40},
        {"monitorID": 25, "status": 0, "time": "2026-08-26 12:10:00", "msg": "timeout", "ping": None},
    ],
    "9": [
        {"monitorID": 9, "status": 1, "time": "2026-08-20 12:00:00", "msg": "OK", "ping": 12},
    ],
}
NOTIFS = [{"id": 2, "name": "hermes-alerts", "type": "apprise", "isDefault": False,
           "config": {"appriseURL": "json://host/?+X-Gitlab-Token=s3cret"}}]
MAINT = [{"id": 1, "title": "nightly", "active": False}]


def make_scripted():
    script = {
        "login": login_ok,
        "getMonitorList": MONITORS,
        "getHeartbeats": HEARTBEATS,
        "getNotifications": NOTIFS,
        "getMaintenance": MAINT,
    }
    t = FakeTransport(script=script)
    c = KumaClient(make_cfg(), transport=t)
    c.ensure_connected()
    return c, t


def test_ack_only_read_uses_multi_argument_push():
    t = FakeTransport(script={"login": login_ok, "getMonitorList": {"ok": True}})
    c = KumaClient(make_cfg(transport_wait=0.2), transport=t)
    c.ensure_connected()
    t.fire_push("monitorList", MONITORS, {"ignored": True})
    assert c.list_monitors()[0]["id"] == 25


# ---------------------------------------------------------------- auth/lifecycle

def test_login_success_on_connect():
    c, t = make_scripted()
    assert c.authenticated is True
    assert ("login", {"username": "u", "password": "p", "token": ""}) in t.emits


def test_bad_credentials_raise_auth_error():
    t = FakeTransport(script={"login": lambda d: {"ok": False, "msg": "Incorrect username."}})
    c = KumaClient(make_cfg(), transport=t)
    with pytest.raises(AuthError):
        c.ensure_connected()


def test_connect_failure_raises_connection_error():
    t = FakeTransport(fail_connect=True)
    c = KumaClient(make_cfg(), transport=t)
    with pytest.raises(ConnectionError_):
        c.ensure_connected()


def test_reconnect_after_drop():
    c, t = make_scripted()
    t.connected = False  # simulate drop
    c.health()            # should transparently reconnect+re-login
    assert t.connected is True


# ---------------------------------------------------------------- reads / fallback

def test_get_monitors_normalized():
    c, _ = make_scripted()
    monitors = c.list_monitors()
    assert [m["id"] for m in monitors] == [25, 9]
    long = [m for m in monitors if m["id"] == 9][0]
    assert long["interval"] == 2073600  # >24h survives


def test_ack_timeout_falls_back_to_push():
    script = {"login": login_ok, "getNotifications": NOTIFS}
    t = FakeTransport(script=script, drop_acks_for=("getNotifications",))
    c = KumaClient(make_cfg(), transport=t)
    c.ensure_connected()

    def late_push():
        t.fire_push("notificationList", NOTIFS)
    import threading
    threading.Timer(0.05, late_push).start()
    notifs = c.list_notifications()
    assert notifs[0]["name"] == "hermes-alerts"


def test_ack_timeout_no_push_times_out():
    script = {"login": login_ok, "getMaintenance": MAINT}
    t = FakeTransport(script=script, drop_acks_for=("getMaintenance",))
    c = KumaClient(make_cfg(transport_wait=0.2), transport=t)
    c.ensure_connected()
    with pytest.raises(TimeoutError_):
        c.list_maintenance()


def test_health_reports_state():
    c, _ = make_scripted()
    h = c.health()
    assert h == {"ok": True, "authenticated": True, "url": "https://kuma.test"}


# ---------------------------------------------------------------- summaries/find

def test_summaries_filter_by_status_down():
    c, _ = make_scripted()
    rows = c.monitor_summaries(status="down")
    assert len(rows) == 1 and rows[0]["id"] == 25
    assert rows[0]["state_label"] == "down"


def test_summaries_keyword_filter():
    c, _ = make_scripted()
    rows = c.monitor_summaries(keyword="cert")
    assert len(rows) == 1 and rows[0]["name"] == "weekly cert"


def test_find_monitors_fuzzy_and_limit():
    c, _ = make_scripted()
    hits = c.find_monitors("sj2")
    assert hits and hits[0]["id"] == 25
    assert c.find_monitors("zzz-none") == []
    assert len(c.find_monitors("", limit=1)) == 1


# ---------------------------------------------------------------- incident context

def test_incident_context_by_name_is_redacted_and_classified():
    c, _ = make_scripted()
    ctx = c.incident_context("mswest1 - SJ2")
    assert ctx["monitor"]["id"] == 25
    assert ctx["state"] == "outage"
    assert ctx["is_real_outage"] is True
    # notification secret must never leak through composite calls either
    assert all("config" not in n for n in ctx["notifications"])
    assert ctx["notifications"][0]["name"] == "hermes-alerts"


def test_incident_context_by_id():
    c, _ = make_scripted()
    ctx = c.incident_context(9)
    assert ctx["monitor"]["id"] == 9
    assert ctx["state"] in ("stale", "healthy")  # old single up beat


def test_incident_context_unknown_monitor_raises():
    c, _ = make_scripted()
    with pytest.raises(KumaError):
        c.incident_context("does-not-exist")


# ---------------------------------------------------------------- redaction everywhere

def test_notification_listing_never_exposes_config():
    c, _ = make_scripted()
    listing = c.list_notifications()
    assert "s3cret" not in str(listing)
