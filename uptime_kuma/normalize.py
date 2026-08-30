"""Normalize raw Kuma Socket.IO payloads into stable, agent-friendly shapes."""
from typing import Any

from .classify import STATUS_LABELS
from .redact import scrub_credentials_in_text


def normalize_monitor(raw: dict) -> dict:
    mtype = raw.get("type")
    target = raw.get("url")
    hostname = raw.get("hostname")
    if target is None and hostname:
        port = raw.get("port")
        target = f"{hostname}:{port}" if port else hostname

    path_name = raw.get("pathName")
    group_path = [p.strip() for p in path_name.split("/") if p.strip()] if path_name else []

    # Scrub embedded credentials at the normalization boundary so every
    # consumer (list, find, incident context, API) inherits a safe value.
    # This is the single scrub point; callers must not re-expose raw URLs.
    if isinstance(target, str):
        target = scrub_credentials_in_text(target)

    tags = raw.get("tags") or []
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "type": mtype,
        "target": target,
        "hostname": hostname,
        "port": raw.get("port"),
        "interval": raw.get("interval"),
        "retry_interval": raw.get("retryInterval"),
        "max_retries": raw.get("maxretries"),
        "active": raw.get("active", True),
        "is_group": mtype == "group",
        "parent_id": raw.get("parentID"),
        "group_path": group_path,
        "tags": [
            {"name": t.get("name"), "value": t.get("value", "")}
            for t in tags
            if isinstance(t, dict)
        ],
    }


def normalize_heartbeat(beat: dict) -> dict:
    status = beat.get("status")
    time_value = beat.get("time")
    if isinstance(time_value, str):
        time_value = time_value.replace(" ", "T", 1)
    return {
        "monitor_id": beat.get("monitorID"),
        "status": status,
        "label": STATUS_LABELS.get(status, "unknown"),
        "time": time_value,
        "msg": beat.get("msg", ""),
        "ping": beat.get("ping"),
    }


def flatten_heartbeats(data: Any) -> list[dict]:
    """Accept {'25': [...]} maps or flat lists; return normalized beats."""
    if not data:
        return []
    collected: list[dict] = []
    if isinstance(data, dict):
        for key, beats in data.items():
            for beat in beats or []:
                item = dict(beat)
                if item.get("monitorID") is None:
                    try:
                        item["monitorID"] = int(key)
                    except (TypeError, ValueError):
                        pass
                collected.append(normalize_heartbeat(item))
    elif isinstance(data, list):
        for beat in data:
            collected.append(normalize_heartbeat(beat))
    return collected
