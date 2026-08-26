"""`kuma` CLI: JSON-first reads, operator-gated mutations, stable exit codes."""
import argparse
import json
import sys
from typing import Any

from .config import Config
from .errors import AuthError, ConnectionError_, KumaError, TimeoutError_
from .kuma_client import KumaClient

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_CONNECTION = 3
EXIT_AUTH = 4
EXIT_TIMEOUT = 5

READ_METHODS = {
    "health": "health",
}


def create_client(cfg: Config | None = None) -> KumaClient:
    return KumaClient(cfg)


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, default=str))
    else:
        print(json.dumps(payload, indent=2, default=str))


# ------------------------------------------------------------------ reads

def cmd_health(client: KumaClient, ns) -> int:
    _emit(client.health(), ns.json)
    return EXIT_OK


def cmd_monitors_list(client: KumaClient, ns) -> int:
    if ns.status or ns.keyword:
        rows = client.monitor_summaries(status=ns.status, keyword=ns.keyword)
    else:
        rows = client.list_monitors()
    _emit(rows, ns.json)
    return EXIT_OK


def cmd_monitors_get(client: KumaClient, ns) -> int:
    from .redact import redact_monitor
    matches = [m for m in client.list_monitors() if str(m["id"]) == str(ns.id)]
    if not matches:
        print(f"no monitor with id {ns.id}", file=sys.stderr)
        return EXIT_ERROR
    from .redact import redact_value
    _emit(redact_value(matches[0]), ns.json)
    return EXIT_OK


def cmd_monitors_find(client: KumaClient, ns) -> int:
    rows = client.find_monitors(ns.query, limit=ns.limit)
    _emit(rows, ns.json)
    return EXIT_OK


def cmd_heartbeats(client: KumaClient, ns) -> int:
    if ns.monitor_id is not None:
        beats = [b for b in client.all_heartbeats_flat() if b["monitor_id"] == ns.monitor_id]
    else:
        beats = client.all_heartbeats_flat()
        if ns.monitor_name:
            target_id = None
            for m in client.find_monitors(ns.monitor_name, limit=1):
                target_id = m["id"]
            beats = [b for b in beats if b["monitor_id"] == target_id]
    if ns.hours is not None:
        import datetime as dt
        cutoff = dt.datetime.now() - dt.timedelta(hours=ns.hours)
        kept = []
        for beat in beats:
            t = beat.get("time")
            try:
                if dt.datetime.fromisoformat(str(t).replace(" ", "T", 1)) >= cutoff:
                    kept.append(beat)
            except ValueError:
                kept.append(beat)
        beats = kept
    beats.sort(key=lambda b: (b["monitor_id"], b["time"] or ""))
    _emit(beats, ns.json)
    return EXIT_OK


def cmd_notifications_list(client: KumaClient, ns) -> int:
    _emit(client.list_notifications(), ns.json)
    return EXIT_OK


def cmd_maintenance_list(client: KumaClient, ns) -> int:
    _emit(client.list_maintenance(), ns.json)
    return EXIT_OK


def cmd_incident_context(client: KumaClient, ns) -> int:
    ctx = client.incident_context(
        ns.monitor if ns.monitor.isdigit() else ns.monitor,
        lookback_minutes=ns.lookback_minutes,
    )
    _emit(ctx, ns.json)
    return EXIT_OK


# ------------------------------------------------------------------ mutations (operator-only)

def _mutate(client: KumaClient, event: str, data: Any) -> dict:
    client.ensure_connected()
    resp = client._transport.emit_ack(event, data, timeout=client.cfg.request_timeout)
    return resp if isinstance(resp, dict) else {"ok": bool(resp), "raw": resp}


def cmd_monitor_pause_resume_delete(client: KumaClient, ns) -> int:
    event_by_action = {
        "pause": ("pauseMonitor", ns.id),
        "resume": ("resumeMonitor", ns.id),
        "delete": ("deleteMonitor", ns.id),
    }
    event, data = event_by_action[ns.action]
    if ns.action == "delete" and not ns.yes:
        print("refusing to delete without --yes", file=sys.stderr)
        return EXIT_USAGE
    resp = _mutate(client, event, data)
    ok = bool(resp.get("ok", False)) if isinstance(resp, dict) else bool(resp)
    _emit({"ok": ok, "action": ns.action, "id": ns.id}, ns.json)
    return EXIT_OK if ok else EXIT_ERROR


def _targets_for_filters(client: KumaClient, ns) -> list[dict]:
    monitors = client.list_monitors()

    def keep(m):
        if ns.group and not any(ns.group.lower() == p.lower() for p in m.get("group_path", [])):
            return False
        if ns.tag and not any(t["name"].lower() == ns.tag.lower() for t in m["tags"]):
            return False
        if ns.name_pattern:
            import fnmatch
            if not fnmatch.fnmatch((m["name"] or "").lower(), ns.name_pattern.lower()):
                return False
        return True

    return [m for m in monitors if keep(m)]


def cmd_bulk_control(client: KumaClient, ns) -> int:
    targets = _targets_for_filters(client, ns)
    names = ", ".join(m["name"] or f"id:{m['id']}" for m in targets)
    if ns.dry_run or not ns.yes:
        _emit({"ok": True, "dry_run": True,
               "would_affect": [{"id": m["id"], "name": m["name"]} for m in targets],
               "note": "pass --yes to apply"}, ns.json)
        if not ns.dry_run:
            print(f"refusing bulk {ns.action} of [{names}] without --yes", file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK

    event = {"pause": "pauseMonitor", "resume": "resumeMonitor", "delete": "deleteMonitor"}[ns.action]
    results = []
    for m in targets:
        resp = _mutate(client, event, m["id"])
        results.append({"id": m["id"], "ok": bool(resp.get("ok", False))})
    failed = sum(1 for r in results if not r["ok"])
    _emit({"total": len(results), "failed": failed, "results": results}, ns.json)
    return EXIT_OK if failed == 0 else EXIT_ERROR


def cmd_bulk_update(client: KumaClient, ns) -> int:
    updates = json.loads(ns.updates) if ns.updates else {}
    if not updates:
        print("--updates JSON required", file=sys.stderr)
        return EXIT_USAGE
    targets = _targets_for_filters(client, ns)
    if ns.dry_run or not ns.yes:
        _emit({"ok": True, "dry_run": True, "updates": updates,
               "would_affect": [{"id": m["id"], "name": m["name"]} for m in targets],
               "note": "pass --yes to apply"}, ns.json)
        return EXIT_OK if ns.dry_run else EXIT_USAGE

    event_map = {"interval": "editMonitor", "retryInterval": "editMonitor",
                 "maxretries": "editMonitor", "timeout": "editMonitor"}
    allowed = {k: v for k, v in updates.items() if k in event_map}
    unknown = set(updates) - set(event_map)
    if unknown:
        print(f"unsupported bulk-update fields: {sorted(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    results = []
    for m in targets:
        try:
            client.update_monitor(m["id"], **allowed)
            ok, err = True, None
        except KumaError as exc:
            ok, err = False, str(exc)[:160]
        row = {"id": m["id"], "ok": ok}
        if err:
            row["error"] = err
        results.append(row)
    failed = sum(1 for r in results if not r["ok"])
    _emit({"total": len(results), "failed": failed, "results": results}, ns.json)
    return EXIT_OK if failed == 0 else EXIT_ERROR


def cmd_set_notifications(client: KumaClient, ns) -> int:
    ids = [int(x) for x in ns.notification_ids.split(",") if x.strip()] if ns.notification_ids else []
    targets = _targets_for_filters(client, ns)
    if ns.dry_run or not ns.yes:
        _emit({"ok": True, "dry_run": True, "notification_ids": ids,
               "would_affect": [{"id": m["id"], "name": m["name"]} for m in targets],
               "note": "pass --yes to apply"}, ns.json)
        return EXIT_OK if ns.dry_run else EXIT_USAGE
    results = []
    for m in targets:
        resp = _mutate(client, "applyMonitorNotification", {"id": m["id"], "notificationIDList": ids})
        results.append({"id": m["id"], "ok": bool(resp.get("ok", False))})
    failed = sum(1 for r in results if not r["ok"])
    _emit({"total": len(results), "failed": failed, "results": results}, ns.json)
    return EXIT_OK if failed == 0 else EXIT_ERROR


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kuma", description="Uptime Kuma operator CLI")
    p.add_argument("--url", dest="cfg_url")
    p.add_argument("--username", dest="cfg_username")
    p.add_argument("--password", dest="cfg_password")
    sub = p.add_subparsers(dest="group")

    def add_read(name, handler):
        sp = sub.add_parser(name)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(handler=handler, read=True)
        return sp

    h = add_read("health", cmd_health)

    mon = sub.add_parser("monitors")
    mon.set_defaults(handler=None)
    monsub = mon.add_subparsers(dest="action")

    ml = monsub.add_parser("list")
    ml.add_argument("--json", action="store_true")
    ml.add_argument("--status")
    ml.add_argument("--keyword")
    ml.set_defaults(handler=cmd_monitors_list)

    mg = monsub.add_parser("get")
    mg.add_argument("--json", action="store_true")
    mg.add_argument("--id", required=True)
    mg.set_defaults(handler=cmd_monitors_get)

    mf = monsub.add_parser("find")
    mf.add_argument("--json", action="store_true")
    mf.add_argument("--query", required=True)
    mf.add_argument("--limit", type=int, default=20)
    mf.set_defaults(handler=cmd_monitors_find)

    hb = add_read("heartbeats", cmd_heartbeats)
    hb.add_argument("--monitor-id", type=int)
    hb.add_argument("--monitor-name")
    hb.add_argument("--hours", type=int)

    nl = sub.add_parser("notifications")
    nl.set_defaults(handler=None)
    nlsub = nl.add_subparsers(dest="action")
    nll = nlsub.add_parser("list")
    nll.add_argument("--json", action="store_true")
    nll.set_defaults(handler=cmd_notifications_list)

    mt = sub.add_parser("maintenance")
    mt.set_defaults(handler=None)
    mtsub = mt.add_subparsers(dest="action")
    mtl = mtsub.add_parser("list")
    mtl.add_argument("--json", action="store_true")
    mtl.set_defaults(handler=cmd_maintenance_list)

    ic = add_read("incident-context", cmd_incident_context)
    ic.add_argument("--monitor", required=True)
    ic.add_argument("--lookback-minutes", type=int, default=60)

    # mutations
    mop = sub.add_parser("monitor")
    mopsub = mop.add_subparsers(dest="action")
    for act in ("pause", "resume", "delete"):
        a = mopsub.add_parser(act)
        a.add_argument("--json", action="store_true")
        a.add_argument("--id", type=int, required=True)
        a.add_argument("--yes", action="store_true")
        a.set_defaults(handler=cmd_monitor_pause_resume_delete, action_name=act)

    bc = sub.add_parser("bulk-control")
    bc.add_argument("--json", action="store_true")
    bc.add_argument("--group"); bc.add_argument("--tag"); bc.add_argument("--name-pattern")
    bc.add_argument("--action", choices=["pause", "resume", "delete"], required=True)
    bc.add_argument("--yes", action="store_true"); bc.add_argument("--dry-run", action="store_true")
    bc.set_defaults(handler=cmd_bulk_control)

    bu = sub.add_parser("bulk-update")
    bu.add_argument("--json", action="store_true")
    bu.add_argument("--group"); bu.add_argument("--tag"); bu.add_argument("--name-pattern")
    bu.add_argument("--updates", help='JSON e.g. \'{"interval":60}\'')
    bu.add_argument("--yes", action="store_true"); bu.add_argument("--dry-run", action="store_true")
    bu.set_defaults(handler=cmd_bulk_update)

    sn = sub.add_parser("set-notifications")
    sn.add_argument("--json", action="store_true")
    sn.add_argument("--group"); sn.add_argument("--tag"); sn.add_argument("--name-pattern")
    sn.add_argument("--notification-ids", help="comma separated ids; empty clears")
    sn.add_argument("--yes", action="store_true"); sn.add_argument("--dry-run", action="store_true")
    sn.set_defaults(handler=cmd_set_notifications)

    return p


def _cfg_from_flags_or_none(ns):
    """Build a Config only when CLI override flags are supplied; else defer."""
    import os

    if not (getattr(ns, "cfg_url", None) or getattr(ns, "cfg_username", None)
            or getattr(ns, "cfg_password", None)):
        return None
    url = getattr(ns, "cfg_url", None) or os.getenv("UPTIME_KUMA_URL", "")
    username = getattr(ns, "cfg_username", None) or os.getenv("UPTIME_KUMA_USERNAME", "")
    password = getattr(ns, "cfg_password", None) or os.getenv("UPTIME_KUMA_PASSWORD", "")
    missing = [n for n, v in (("url", url), ("username", username), ("password", password)) if not v]
    if missing:
        raise KumaError(f"missing required connection settings: {', '.join(missing)}")
    return Config(url=url.rstrip("/"), username=username, password=password)


def main(argv=None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if getattr(ns, "handler", None) is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    try:
        cfg = _cfg_from_flags_or_none(ns)
        client = create_client() if cfg is None else create_client(cfg)
        return ns.handler(client, ns)
    except ConnectionError_ as exc:
        print(f"connection error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION
    except AuthError as exc:
        print(f"auth error: {exc}", file=sys.stderr)
        return EXIT_AUTH
    except TimeoutError_ as exc:
        print(f"timeout: {exc}", file=sys.stderr)
        return EXIT_TIMEOUT
    except KumaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
