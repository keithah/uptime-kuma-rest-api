"""Heartbeat status labels and incident classification."""
import datetime as dt
from typing import Any

STATUS_LABELS = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}

DEFAULT_FRESHNESS_SECONDS = 120  # max(interval*3, this)


def label_for_status(status: int) -> str:
    return STATUS_LABELS.get(status, "unknown")


def parse_time(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def classify_state(
    beats: list[dict],
    now: Any = None,
    lookback_minutes: int = 60,
    interval: int | None = None,
) -> str:
    """Classify one monitor's recent beats into a coarse state label.

    Ordering matters: maintenance/flapping/outage/recovery are decided before
    staleness so an unresolved outage stays an outage even if beats stop.
    """
    parsed = []
    for beat in beats:
        t = parse_time(beat.get("time"))
        if t is not None:
            parsed.append((t, beat))
    parsed.sort(key=lambda pair: pair[0])
    if not parsed:
        return "unknown"

    now_dt = parse_time(now) if now is not None else parsed[-1][0]
    if now_dt is None:
        now_dt = parsed[-1][0]

    window_start = now_dt - dt.timedelta(minutes=lookback_minutes)
    windowed = [(t, b) for t, b in parsed if t >= window_start]
    if not windowed:
        windowed = [parsed[-1]]

    latest_t, latest_beat = windowed[-1]
    latest_status = latest_beat.get("status")

    if latest_status == 3:
        return "maintenance"

    statuses = [b.get("status") for _, b in windowed]
    transitions = sum(
        1 for a, b in zip(statuses, statuses[1:]) if a != b  # noqa: RUF007 - pairwise reads worse here
    )
    if transitions >= 3:
        return "flapping"

    if latest_status == 0:
        return "outage"

    if latest_status == 1 and any(s == 0 for s in statuses[:-1]):
        return "recovery"

    threshold = max((interval or 0) * 3, DEFAULT_FRESHNESS_SECONDS)
    if (now_dt - latest_t).total_seconds() > threshold:
        return "stale"

    return "healthy"


def build_incident_context(
    monitor: dict,
    beats: list[dict],
    notifications: list | None = None,
    maintenance: list | None = None,
    now: Any = None,
    lookback_minutes: int = 60,
) -> dict:
    notifications = notifications or []
    maintenance = maintenance or []

    state = classify_state(beats, now=now, lookback_minutes=lookback_minutes,
                           interval=monitor.get("interval"))

    parsed = []
    for beat in beats:
        t = parse_time(beat.get("time"))
        if t is not None:
            parsed.append((t, beat))
    parsed.sort(key=lambda pair: pair[0])

    now_dt = parse_time(now) if now is not None else (parsed[-1][0] if parsed else None)
    window_start = (now_dt - dt.timedelta(minutes=lookback_minutes)) if now_dt else None
    windowed = [
        (t, b) for t, b in parsed if window_start is None or t >= window_start
    ] or parsed

    total = len(windowed)
    downs = sum(1 for _, b in windowed if b.get("status") == 0)
    pings = [b.get("ping") for _, b in windowed if b.get("ping") is not None]

    latest_beat = (windowed[-1][1] if windowed else {})
    # Maintenance masking must be scoped to this monitor: a window for a
    # different monitor must not suppress is_real_outage. When the
    # maintenance payload carries monitor association (monitorID,
    # monitor_id, monitors, monitorList, affectedMonitors, etc.) we check
    # it; when no association is present the window is treated as
    # monitor-agnostic (preserves backward compat for legacy tests).
    def _window_applies_to_monitor(window: dict, monitor_id: Any) -> bool:
        # Direct single-monitor linkage.
        for key in ("monitorID", "monitorId", "monitor_id", "monitorIDList"):
            if key in window:
                val = window[key]
                if isinstance(val, (list, tuple, set)):
                    if monitor_id in val or str(monitor_id) in {str(x) for x in val}:
                        return True
                elif val == monitor_id or str(val) == str(monitor_id):
                    return True
                # Present but does not match -> this window is for another monitor.
                return False
        # Multi-monitor linkage.
        for key in ("monitors", "monitorList", "affectedMonitors", "monitorIDs", "monitor_ids"):
            if key in window:
                val = window[key]
                candidates: list[Any] = []
                if isinstance(val, dict):
                    candidates = list(val.keys()) + list(val.values())
                elif isinstance(val, (list, tuple, set)):
                    candidates = list(val)
                else:
                    candidates = [val]
                # Normalize candidates that may be dicts with id fields.
                normalized: set[str] = set()
                for c in candidates:
                    if isinstance(c, dict):
                        for k in ("id", "monitorID", "monitorId", "monitor_id"):
                            if k in c:
                                normalized.add(str(c[k]))
                    else:
                        normalized.add(str(c))
                return str(monitor_id) in normalized
        # No association field -> treat as global (backward compat).
        return True

    monitor_id = monitor.get("id")
    scoped_active = False
    for w in maintenance:
        if not w.get("active"):
            continue
        if monitor_id is None or _window_applies_to_monitor(w, monitor_id):
            scoped_active = True
            break
    in_maintenance_window = scoped_active or latest_beat.get("status") == 3

    is_real_outage = (
        state == "outage"
        and not in_maintenance_window
        and latest_beat.get("status") == 0
    )

    return {
        "monitor": monitor,
        "state": state,
        "lookback_minutes": lookback_minutes,
        "current": {
            "status": latest_beat.get("status"),
            "label": label_for_status(latest_beat.get("status")) if latest_beat else "unknown",
            "time": latest_beat.get("time") if latest_beat else None,
            "msg": latest_beat.get("msg", "") if latest_beat else "",
            "ping": latest_beat.get("ping") if latest_beat else None,
        },
        "timeline": [
            {"time": b.get("time"), "label": label_for_status(b.get("status")),
             "msg": b.get("msg", ""), "ping": b.get("ping")}
            for _, b in windowed
        ],
        "failure_rate": round(downs / total, 4) if total else 0.0,
        "avg_ping": round(sum(pings) / len(pings), 1) if pings else None,
        "notifications": notifications,
        "maintenance_windows": maintenance,
        "is_real_outage": is_real_outage,
    }
