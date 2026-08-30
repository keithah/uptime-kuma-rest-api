# Design: Uptime Kuma Integration Rewrite

Date: 2026-08-26
Status: Approved (research phase concluded; direction chosen by Keith)

## Problem
Hermes investigates Uptime Kuma alerts via webhook-triggered runs. Today that
investigation shells out over SSH, copies a multi-GB SQLite DB, and hand-parses
monitor state. There is no structured, safe, low-context way for an agent to
answer "what exactly is alerting, what changed, and is it real?"

## Decision (from research phase)
Layered architecture, one canonical Kuma client core, three thin surfaces:

- **Core** — shared Socket.IO client + normalization + redaction + status
  classification.
- **CLI** — deterministic operator surface (JSON out, stable exit codes).
  Mutating verbs are operator-only.
- **Read-only MCP adapter** — the agent-facing surface for incident
  investigation. No write/delete tools exist in it at all.
- **REST API** — kept (rewritten) for curl/script parity; same core.

The existing webhook → Hermes investigation flow stays as-is; the skill gains
structured tools instead of SSH/sqlite archaeology.

Printing Press packaging is explicitly deferred until the interface stabilizes.

## Non-goals
- Multi-instance Kuma support (config shaped so it can be added later).
- Writes over MCP (never).
- Replacing the webhook ingress.

## Layout

```
uptime_kuma/
  __init__.py
  errors.py        # error taxonomy -> JSON codes
  config.py        # env/.env loading + validation
  transport.py     # minimal Socket.IO wrapper interface (fake-able in tests)
  kuma_client.py   # auth, calls (ack-first, push-fallback), reconnect
  normalize.py     # raw monitor/heartbeat/notification dicts -> clean shapes
  redact.py        # recursive secret scrubbing
  classify.py      # status labels + incident_context builder
  cli.py           # `kumactl` argparse CLI
  mcp_server.py    # read-only MCP server (stdio + streamable-http via kumactl-mcp --transport streamable-http)
api_server.py      # Flask REST app (replaces uptime_kuma_rest_api.py)
tests/             # pytest, offline fakes only
scripts/smoke_live.sh  # manual live check against real Kuma
docs/design-2026-08-25-rewrite.md
```

Python >= 3.10. Deps: flask, python-socketio[client], python-dotenv, mcp,
pytest (dev).

## Kuma API notes (v2.x)

- Primary API is Socket.IO (path `/socket.io`), not REST.
- Auth: `login` event `{username, password, token:""}` with ack callback;
  `loginByToken` for JWT. 2FA unsupported here (single user, none enabled).
- Data: most reads have ack callbacks (`getMonitorList`, `getHeartbeats`,
  `getNotifications`, `getMaintenance`, `getSettings`); pushes (`monitorList`,
  `heartbeatList`, ...) also fire. Client uses **ack-first, push-fallback**,
  with a bounded wait and clear timeout errors.
- Mutations (`addMonitor`, `editMonitor`, `deleteMonitor`, `pauseMonitor`,
  `resumeMonitor`, notification CRUD) are exposed **only** via REST/CLI, never MCP.
- Heartbeat status ints: 0=DOWN, 1=UP, 2=PENDING, 3=MAINTENANCE.

## Redaction rules (enforced in one place, applied everywhere)

Scrub values of keys matching (case-insensitive): password, passwd, secret,
token, api_key, bearer, basic_auth_user/pass, oauth_client_secret,
radiusPassword/Secret, mqttPassword, rabbitmqPassword, smtpPassword,
headers, pushToken, databaseConnectionString, tlsCert/tlsKey/tlsCa,
slackWebhookURL, webhookURL, discordWebhookUrl, gotifyapplicationToken,
pushcode. Additionally scrub `scheme://user:pass@` inside any string value.
Notification listings keep only: id, name, type, isDefault, active, applyExisting.

Redaction is total (no include-secrets escape hatch).

## Status classification (classify.py)

Given heartbeats for one monitor within `lookback_minutes` (default 60):

- `outage`     — latest beat DOWN, no later UP
- `recovery`   — latest beat UP, ≥1 DOWN inside window
- `flapping`   — ≥3 status transitions inside window
- `stale`      — newest beat older than max(interval*3, 120s)
- `maintenance`— current beat status 3 or inside a maintenance window
- `healthy`    — everything else

`incident_context(monitor, lookback_minutes)` returns: monitor identity
(id/name/type/target/group path/interval/retries), current state +
classification, transition timeline, failure rate, avg ping (windowed),
cert expiry when present, attached notification names/types (redacted),
overlapping maintenance windows, and `is_real_outage` convenience bool
(outage AND not maintenance AND beats are fresh).

## Surfaces

### MCP (read-only; the agent surface)

| Tool | Purpose |
|---|---|
| `kuma_health()` | connectivity + auth + version |
| `kuma_list_monitor_summaries(status?, keyword?)` | compact per-monitor status |
| `kuma_find_monitors(query, limit=20)` | fuzzy name/tag search |
| `kuma_get_monitor(monitor_id)` | full (redacted) config |
| `kuma_get_heartbeats(monitor_id, hours=24)` | beat history |
| `kuma_incident_context(monitor, lookback_minutes=60)` | the money tool |
| `kuma_list_notifications()` | redacted channels |
| `kuma_list_maintenance()` | windows |

Transport: `kumactl-mcp --transport streamable-http` (native Streamable HTTP, `stateless_http=False`) is the Hermes default; stdio remains available via `kumactl-mcp --transport stdio`.

### CLI (`kumactl`, exit 0 ok / 2 usage / 3 connection / 4 auth / 5 timeout)

Reads: `health`, `monitors list|find|get`, `heartbeats`, `notifications list`,
`maintenance list`, `incident-context`. All `--json` capable.
Operator verbs: `monitor add|edit|pause|resume|delete`, `bulk-update`,
`bulk-control`, `set-notifications`. Destructive ops require explicit
`--yes`; name-pattern deletes print the target set first.

### REST (Flask, default 127.0.0.1:5001)

Same operations as today's README (list/create/update/delete monitors,
bulk ops, notification CRUD/test/assignment, settings) plus new
`GET /incident-context?monitor=<id|name>&lookback_minutes=60`.
All outputs pass through the shared redactor. Consistent envelope:
`{"ok": true, ...}` / `{"ok": false, "error": {"code", "message"}}`.

## Config

Env (or `.env`): `UPTIME_KUMA_URL`, `UPTIME_KUMA_USERNAME`,
`UPTIME_KUMA_PASSWORD`, optional `UPTIME_KUMA_SOCKET_PATH` and
`UPTIME_KUMA_TIMEOUT`. The optional Flask adapter binds to `127.0.0.1:5001`;
credentials are never logged and config dumps mask them.

## Testing strategy

pytest, fully offline: a fake transport replays scripted ack/push sequences.
Suites cover: client auth + ack/push fallback + timeouts, normalization,
redaction (incl. nested + URL-embedded creds), classification matrix,
CLI JSON/exit codes, MCP tool registry == read-only set, Flask endpoints.
Live smoke (`scripts/smoke_live.sh`) runs only with explicit env.

## Deployment (this Mac — the Hermes gateway host)

Note: this deployment section reflects the author's own host layout; adapt
paths to your machine. Everything runs locally on the gateway host.

- Code at `~/src/kumactl` (cloned from `keithah/kumactl`), uv venv, `uv pip install -e .`.
- Env file `~/.hermes/kuma.env` (0600) written from 1Password item
  `uptime kuma` (vault Hermes); never committed. Wrapper prefers `KUMACTL_ENV_FILE` with `KUMA_ENV_FILE` fallback.
- Hermes `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  kumactl:
    command: /absolute/path/to/kumactl/bin/kumactl-mcp-wrapper
    args: ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "40108", "--path", "/mcp"]
    connect_timeout: 30
    timeout: 60
```

  Wrapper sources the env file then execs `.venv/bin/kumactl-mcp` (needed because
  Hermes filters subprocess env). Native transport: `kumactl-mcp --transport streamable-http --host 127.0.0.1 --port 40108 --path /mcp`.

- For HTTP, register with Hermes as:

```bash
hermes mcp add kumactl --url http://127.0.0.1:40108/mcp
```

- REST surface optional here; runnable ad hoc (`python api_server.py`) or as a
  LaunchAgent later. MCP stdio needs no daemon; HTTP needs the launchd service `net.hadm.mcp-http.kumactl`.
- Gateway restart required for MCP registration (agent restart picks up new
  tools); verify with tool listing after restart.

## Risks / follow-ups

- Kuma Socket.IO API is internal; pinned against live 2.5.3 via smoke test.
- Long-interval monitors (>24h) must survive normalization (upstream MCP bug #44 lesson).
- Printing Press packaging deferred; revisit once surfaces stabilize.
