"""Tests for pure-logic core modules: errors, redact, normalize, classify, config."""
import pytest

from uptime_kuma.errors import KumaError, AuthError, ConnectionError_, TimeoutError_
from uptime_kuma.redact import redact_value, redact_monitor, redact_notification
from uptime_kuma.normalize import normalize_monitor, normalize_heartbeat, flatten_heartbeats
from uptime_kuma.classify import (
    STATUS_LABELS, label_for_status, classify_state,
    build_incident_context,
)
from uptime_kuma.config import Config


# ---------------------------------------------------------------- errors

def test_error_codes_are_stable():
    assert ConnectionError_("x").code == "connection_error"
    assert AuthError("x").code == "auth_error"
    assert TimeoutError_("x").code == "timeout"
    e = KumaError("boom")
    assert e.code == "kuma_error" and str(e) == "boom"


# ---------------------------------------------------------------- redact

SECRET_KEYS = [
    "password", "PASSWORD", "smtpPassword", "basic_auth_pass",
    "bearer_token", "oauth_client_secret", "mqttPassword",
    "rabbitmqPassword", "radiusSecret", "pushToken",
    "databaseConnectionString", "headers", "tlsCert", "slackWebhookURL",
    "webhookURL", "discordWebhookUrl", "gotifyapplicationToken",
    "apiKey", "API_KEY", "secret", "authValue",
]

@pytest.mark.parametrize("key", SECRET_KEYS)
def test_secret_keys_scrubbed(key):
    out = redact_value({key: "hunter2"})
    assert out[key] == "***"


def test_url_embedded_credentials_scrubbed():
    out = redact_value({"url": "http://admin:hunter2@host:2375"})
    assert "hunter2" not in out["url"]
    assert out["url"].startswith("http://***")


def test_nested_redaction_recursive():
    data = {
        "ok": 1,
        "nested": {"password": "p", "list": [{"token": "t"}, "plain"]},
    }
    out = redact_value(data)
    assert out["nested"]["password"] == "***"
    assert out["nested"]["list"][0]["token"] == "***"
    assert out["nested"]["list"][1] == "plain"
    # original untouched
    assert data["nested"]["password"] == "p"


def test_notification_listing_minimal_fields():
    raw = {
        "id": 3, "name": "hermes-alerts", "type": "apprise",
        "isDefault": True, "active": True, "applyExisting": False,
        "config": {"appriseURL": "json://host/webhook?+X-Gitlab-Token=s3cret"},
    }
    out = redact_notification(raw)
    assert set(out.keys()) <= {"id", "name", "type", "isDefault", "active", "applyExisting"}
    assert "s3cret" not in str(out)


def test_redact_monitor_keeps_useful_fields_hides_secrets():
    mon = {
        "id": 25, "name": "mswest1 - SJ2", "type": "http",
        "url": "http://user:pw@example.test/health",
        "basic_auth_user": "u", "basic_auth_pass": "pw",
        "hostname": "example.test", "interval": 60,
    }
    out = redact_monitor(mon)
    assert out["id"] == 25 and out["interval"] == 60  # useful stays
    assert out["basic_auth_pass"] == "***"            # secret goes
    assert "pw@" not in out["url"]
    assert "user:" not in out["url"].split("example")[0] or "***" in out["url"]


# ---------------------------------------------------------------- normalize

def test_normalize_monitor_long_interval_survives():
    """Regression guard (upstream bug #44): interval > 86400 must survive."""
    raw = {
        "id": 7, "name": "weekly cert check", "type": "http",
        "url": "https://cert.example/", "interval": 2073600,
        "active": True, "tags": [{"name": "prod", "value": ""}],
    }
    m = normalize_monitor(raw)
    assert m["interval"] == 2073600
    assert m["target"] == "https://cert.example/"
    assert m["tags"] == [{"name": "prod", "value": ""}]
    assert m["group_path"] == []  # no pathName given -> empty


def test_normalize_monitor_group_and_parent():
    raw = {"id": 9, "name": "kid", "type": "group", "parentID": 4,
           "pathName": "Prod / Web"}
    m = normalize_monitor(raw)
    assert m["is_group"] is True and m["parent_id"] == 4
    assert m["group_path"] == ["Prod", "Web"]


def test_normalize_monitor_target_variants():
    assert normalize_monitor({"id": 1, "name": "a", "type": "http", "url": "http://x/"})["target"] == "http://x/"
    assert normalize_monitor({"id": 2, "name": "b", "type": "ping", "hostname": "h"})["target"] == "h"
    port_mon = normalize_monitor({"id": 3, "name": "c", "type": "port", "hostname": "h", "port": 5432})
    assert port_mon["target"] == "h:5432"
    assert normalize_monitor({"id": 4, "name": "d", "type": "docker"})["target"] is None


def test_normalize_heartbeat_fields_and_iso_time():
    beat = {"monitorID": 25, "status": 1, "time": "2026-08-26 06:55:00.123",
            "msg": "200 - OK", "ping": 42}
    b = normalize_heartbeat(beat)
    assert b["status"] == 1 and b["label"] == "up"
    assert b["time"].startswith("2026-08-26T06:55:00")
    assert b["ping"] == 42 and b["monitor_id"] == 25


def test_flatten_heartbeats_accepts_both_shapes():
    keyed = {"25": [{"monitorID": 25, "status": 1, "time": "2026-08-26 00:00:00"}],
             "9": [{"monitorID": 9, "status": 0, "time": "2026-08-26 00:00:00"}]}
    flat = flatten_heartbeats(keyed)
    assert len(flat) == 2 and {b["monitor_id"] for b in flat} == {25, 9}

    plain = [{"monitorID": 25, "status": 1, "time": "2026-08-26 00:00:00"}]
    assert len(flatten_heartbeats(plain)) == 1
    assert flatten_heartbeats(None) == []


# ---------------------------------------------------------------- classify

def test_status_labels_complete():
    assert STATUS_LABELS == {0: "down", 1: "up", 2: "pending", 3: "maintenance"}
    assert label_for_status(1) == "up"


def _beat(status, seconds, base=None):
    import datetime as dt
    t = (base or dt.datetime(2026, 8, 26, 12, 0, 0)) + dt.timedelta(seconds=seconds)
    return {"monitor_id": 25, "status": status, "label": label_for_status(status),
            "time": t.isoformat(), "msg": "", "ping": 50}


def test_classify_outage_latest_down_no_recovery():
    beats = [_beat(1, 0), _beat(0, 120)]
    assert classify_state(beats, now=_beat(0, 999)["time"]) == "outage"


def test_classify_recovery_up_after_down_in_window():
    beats = [_beat(0, 0), _beat(0, 60), _beat(1, 300)]
    assert "recovery" in classify_state(beats)


def test_classify_flapping_many_transitions():
    beats = [_beat(1, 0), _beat(0, 30), _beat(1, 60), _beat(0, 90)]
    assert classify_state(beats) == "flapping"


def test_classify_stale_old_beats():
    beats = [_beat(1, -100000)]  # way old
    assert classify_state(beats, now=_beat(1, 0)["time"]) == "stale"


def test_classify_maintenance_status_beat():
    beats = [_beat(3, 0)]
    assert classify_state(beats) == "maintenance"


def test_classify_empty_is_unknown():
    assert classify_state([]) == "unknown"


def test_incident_context_shape_and_real_outage_flag():
    mon = normalize_monitor({"id": 25, "name": "mswest1 - SJ2", "type": "http",
                             "url": "http://plex:3002/x", "interval": 60})
    beats = [_beat(1, -600), _beat(0, -120)]
    ctx = build_incident_context(
        monitor=mon, beats=beats, notifications=[{"name": "hermes-alerts", "type": "apprise"}],
        maintenance=[], now=_beat(0, 0)["time"],
    )
    assert ctx["monitor"]["id"] == 25
    assert ctx["state"] == "outage"
    assert ctx["is_real_outage"] is True
    assert ctx["failure_rate"] > 0
    assert ctx["notifications"][0]["name"] == "hermes-alerts"
    assert "timeline" in ctx and len(ctx["timeline"]) == 2


def test_incident_context_maintenance_not_real_outage():
    mon = normalize_monitor({"id": 1, "name": "x", "type": "http", "url": "http://x/",
                             "interval": 60})
    beats = [_beat(0, -60)]
    maint = [{"title": "window", "active": True}]
    ctx = build_incident_context(monitor=mon, beats=beats, notifications=[],
                                 maintenance=maint, now=_beat(0, 0)["time"])
    assert ctx["state"] == "outage"
    assert ctx["is_real_outage"] is False


# ---------------------------------------------------------------- config

def test_config_requires_url_username_password(monkeypatch):
    for var in ("UPTIME_KUMA_URL", "UPTIME_KUMA_USERNAME", "UPTIME_KUMA_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(KumaError):
        Config.from_env()

    monkeypatch.setenv("UPTIME_KUMA_URL", "https://uptime.hadm.net")
    monkeypatch.setenv("UPTIME_KUMA_USERNAME", "keith")
    monkeypatch.setenv("UPTIME_KUMA_PASSWORD", "pw")
    cfg = Config.from_env()
    assert cfg.url == "https://uptime.hadm.net"
    assert cfg.username == "keith"
    assert cfg.password == "pw"
    masked = repr(cfg.masked()) 
    assert "pw" not in masked and "keith" in masked


def test_config_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("UPTIME_KUMA_URL", "https://uptime.hadm.net/")
    monkeypatch.setenv("UPTIME_KUMA_USERNAME", "u")
    monkeypatch.setenv("UPTIME_KUMA_PASSWORD", "p")
    assert Config.from_env().url == "https://uptime.hadm.net"
