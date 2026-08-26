"""Canonical Uptime Kuma client: auth, ack-first/push-fallback reads, orchestration."""
import fnmatch
import threading
from typing import Any

from .classify import build_incident_context, classify_state, label_for_status
from .config import Config
from .errors import AuthError, ConnectionError_, KumaError, TimeoutError_
from .normalize import flatten_heartbeats, normalize_monitor
from .redact import redact_notification, scrub_credentials_in_text


class KumaClient:
    """Thread-safe-ish client; one logical session per instance."""

    def __init__(self, cfg: Config | None = None, transport: Any | None = None):
        self.cfg = cfg or Config.from_env()
        if transport is not None:
            self._transport = transport
            self._owns_transport = False
        else:
            from .transport import SocketIOTransport  # local import: test fakeability
            self._transport = SocketIOTransport(self.cfg)
            self._owns_transport = True

        self.authenticated = False
        self._lock = threading.RLock()
        self._install_push_handlers()

    # ------------------------------------------------------------ lifecycle

    def _install_push_handlers(self):
        self._push_lock = threading.Lock()
        self._latest_pushes: dict[str, Any] = {}
        for event in ("monitorList", "heartbeatList", "notificationList",
                      "maintenanceList", "importantHeartbeatList"):
            def make_handler(evt):
                def handler(*payloads):
                    # Kuma emits some events as (primary_payload, auxiliary_payloads...).
                    payload = next((item for item in payloads if isinstance(item, (dict, list))), None)
                    with self._push_lock:
                        self._latest_pushes[evt] = payload
                return handler
            self._transport.on(event, make_handler(event))

    def ensure_connected(self) -> None:
        with self._lock:
            if self._transport.connected and self.authenticated:
                return
            try:
                self._transport.connect()
            except KumaError:
                raise
            except Exception as exc:
                raise ConnectionError_(f"transport connect to {self.cfg.url} failed: {exc}") from exc

            resp = self._transport.emit_ack(
                "login",
                {"username": self.cfg.username, "password": self.cfg.password, "token": ""},
                timeout=self.cfg.request_timeout,
            ) or {}
            if resp.get("ok"):
                self.authenticated = True
                self.token = resp.get("token")
            elif resp.get("token") and not resp.get("ok") is False:
                # some versions reply {"token": ...} on success via loginByToken path
                self.authenticated = True
                self.token = resp["token"]
            else:
                msg = resp.get("msg") or "authentication failed"
                raise AuthError(f"Kuma rejected credentials: {msg}")

    def close(self) -> None:
        if self._owns_transport:
            self._transport.close()

    # ------------------------------------------------------------ plumbing

    def _call(self, event: str, data: Any = None) -> Any:
        return self._transport_emit_with_reconnect(event, data)

    def _read_with_fallback(self, event: str, push_event: str) -> Any:
        """Ack first; on timeout wait briefly for the push variant before giving up."""
        try:
            result = self._transport_emit_with_reconnect(event)
            # Kuma often acknowledges the request with {ok: true} and sends
            # the actual collection asynchronously on the matching push event.
            if not (isinstance(result, dict) and result.get("ok") is True):
                return result
        except TimeoutError_:
            pass

        waited = 0.0
        step = 0.05
        while waited < self.cfg.transport_wait:
            with self._push_lock:
                if push_event in self._latest_pushes:
                    return self._latest_pushes[push_event]
            threading.Event().wait(step)
            waited += step
        raise TimeoutError_(f"no ack and no '{push_event}' push for {event}")

    def _transport_emit_with_reconnect(self, event: str, data: Any = None) -> Any:
        self.ensure_connected()
        try:
            return self._transport.emit_ack(event, data, timeout=self.cfg.request_timeout)
        except (ConnectionError_, ConnectionError, OSError):
            with self._lock:
                self.authenticated = False
                self._transport.connected = False
                self.ensure_connected()
            return self._transport.emit_ack(event, data, timeout=self.cfg.request_timeout)

    # ------------------------------------------------------------ reads

    def health(self) -> dict:
        self.ensure_connected()
        return {
            "ok": True,
            "authenticated": self.authenticated,
            "url": self.cfg.url,
        }

    def list_monitors_raw(self) -> dict:
        resp = self._read_with_fallback("getMonitorList", "monitorList")
        return resp.get("monitorList", {}) if isinstance(resp, dict) and "monitorList" in resp else (resp or {})

    def list_monitors(self) -> list[dict]:
        data = self.list_monitors_raw() or {}
        monitors = [normalize_monitor(m) for m in (data.values() if isinstance(data, dict) else data)]
        monitors.sort(key=lambda m: (m.get("name") or "").lower())
        return monitors

    def get_heartbeats(self) -> dict:
        resp = self._read_with_fallback("getHeartbeats", "heartbeatList")
        if isinstance(resp, dict):
            return resp.get("heartbeatList", resp)
        return {}

    def get_monitor_heartbeats(self, monitor_id: int) -> list[dict]:
        resp = self._call("getMonitorHeartbeats", monitor_id)
        beats = resp.get("heartbeatList", []) if isinstance(resp, dict) else []
        return flatten_heartbeats(beats)

    def all_heartbeats_flat(self) -> list[dict]:
        return flatten_heartbeats(self.get_heartbeats())

    def list_notifications(self) -> list[dict]:
        resp = self._read_with_fallback("getNotifications", "notificationList")
        rows = resp.get("notificationList", []) if isinstance(resp, dict) and "notificationList" in resp else (resp or [])
        return [redact_notification(n) for n in rows]

    def list_maintenance(self) -> list[dict]:
        resp = self._read_with_fallback("getMaintenance", "maintenanceList")
        if isinstance(resp, dict):
            for key in ("maintenanceList", "maintenance"):
                if key in resp:
                    return resp[key]
        return resp if isinstance(resp, list) else []

    # ------------------------------------------------------------ derived views

    def monitor_summaries(
        self,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[dict]:
        monitors = {m["id"]: m for m in self.list_monitors()}
        beats_by_monitor: dict[int, list[dict]] = {}
        for beat in self.all_heartbeats_flat():
            beats_by_monitor.setdefault(beat["monitor_id"], []).append(beat)

        rows = []
        for mid, mon in monitors.items():
            beats = sorted(beats_by_monitor.get(mid, []), key=lambda b: b["time"])
            latest = beats[-1] if beats else None
            label = label_for_status(latest["status"]) if latest else "unknown"
            row = {
                "id": mid,
                "name": mon["name"],
                "type": mon["type"],
                "target": redact_safe_target(mon),
                "state_label": label,
                "state": classify_state(beats, interval=mon.get("interval")),
                "last_msg": latest.get("msg", "") if latest else "",
                "last_time": latest.get("time") if latest else None,
                "interval": mon.get("interval"),
            }
            if status and row["state_label"] != str(status).lower():
                continue
            if keyword and str(keyword).lower() not in f"{mon['name']} {mon['target']}".lower():
                continue
            rows.append(row)
        rows.sort(key=lambda r: r["name"].lower())
        return rows

    def find_monitors(self, query: str, limit: int = 20) -> list[dict]:
        q = (query or "").lower().strip()
        out = []
        for mon in self.list_monitors():
            hay = f"{mon['name']} {' '.join((t.get('name') or '') + ' ' + (t.get('value') or '') for t in mon['tags'])}".lower()
            if q in hay or fnmatch.fnmatch(mon["name"] or "", f"*{q}*"):
                out.append(mon)
                if len(out) >= limit:
                    break
        return out

    # ------------------------------------------------------------ mutations

    @staticmethod
    def _notification_list_to_map(value: Any) -> dict:
        """Kuma's editMonitor expects notificationIDList as {id_str: true}."""
        if isinstance(value, dict):
            return value
        if isinstance(value, (list, tuple)):
            return {str(nid): True for nid in value if isinstance(nid, int)}
        raise KumaError(f"unsupported notificationIDList shape: {type(value).__name__}")

    def update_monitor(self, monitor_id: int, **fields) -> dict:
        """Edit a monitor by sending the FULL object (v2 editMonitor is a
        replace, not a patch) with `fields` applied on top."""
        monitors = self.list_monitors_raw()
        rows = list(monitors.values()) if isinstance(monitors, dict) else monitors
        current = next((m for m in rows if m.get("id") == monitor_id), None)
        if current is None:
            raise KumaError(f"no monitor with id {monitor_id}")
        payload = dict(current)
        payload.update(fields)
        if "notificationIDList" in payload:
            payload["notificationIDList"] = self._notification_list_to_map(
                payload["notificationIDList"])
        resp = self._transport_emit_with_reconnect("editMonitor", payload)
        if not (isinstance(resp, dict) and resp.get("ok")):
            msg = resp.get("msg") if isinstance(resp, dict) else resp
            raise KumaError(f"editMonitor failed for monitor {monitor_id}: {msg}")
        return resp

    # ------------------------------------------------------------ composite

    def incident_context(self, monitor: int | str, lookback_minutes: int = 60) -> dict:
        monitors = self.list_monitors()
        found = None
        if isinstance(monitor, int) or (isinstance(monitor, str) and monitor.isdigit()):
            want = int(monitor)
            found = next((m for m in monitors if m["id"] == want), None)
        if found is None:
            needle = str(monitor).lower().strip()
            candidates = [
                m for m in monitors
                if needle in (m["name"] or "").lower()
                or any(needle == (t.get("name") or "").lower() or needle in (t.get("name") or "").lower()
                       for t in m["tags"])
            ]
            exact = [m for m in candidates if (m["name"] or "").lower() == needle]
            found = exact[0] if exact else (candidates[0] if candidates else None)
        if found is None:
            raise KumaError(f"no monitor matches {monitor!r}")

        beats = [b for b in self.all_heartbeats_flat() if b["monitor_id"] == found["id"]]
        notifications = self.list_notifications()
        maintenance = self.list_maintenance()

        return build_incident_context(
            monitor=found,
            beats=beats,
            notifications=notifications,
            maintenance=maintenance,
            lookback_minutes=lookback_minutes,
        )


def redact_safe_target(mon: dict) -> str | None:
    """Monitor target with any embedded user:pass@ credentials masked."""
    target = mon.get("target")
    if isinstance(target, str):
        return scrub_credentials_in_text(target)
    return None
