"""REST adapter for the rewritten Kuma client."""
import json

import pytest

from uptime_kuma import api_server
import test_client as tc


@pytest.fixture()
def app(monkeypatch):
    client, _ = tc.make_scripted()
    monkeypatch.setattr(api_server, "create_client", lambda: client)
    return api_server.create_app({"TESTING": True})


def test_incident_context_returns_json(app):
    response = app.test_client().get("/incident-context", query_string={"monitor": "mswest1 - SJ2"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["state"] == "outage"
    assert data["is_real_outage"] is True
    assert "s3cret" not in json.dumps(data)


def test_incident_context_requires_monitor(app):
    response = app.test_client().get("/incident-context")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_incident_context_maps_unknown_monitor(app):
    response = app.test_client().get("/incident-context", query_string={"monitor": "missing"})
    assert response.status_code == 404
    assert response.get_json()["code"] == "kuma_error"


def test_health_endpoint(app):
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
