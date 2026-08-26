# uptime-kuma-rest-api

Python client + tooling for [Uptime Kuma](https://github.com/louislam/uptime-kuma) v2:
a redacted, typed core client over Socket.IO, an operator CLI, a read-only MCP
server for agent integrations, and an optional Flask REST adapter.

## Install

```bash
git clone https://github.com/keithah/uptime-kuma-rest-api.git
cd uptime-kuma-rest-api
uv pip install -e .        # or: pip install -e .
```

## Configuration

Credentials come from the environment (or `~/.kuma.env`, sourced however you like):

```bash
UPTIME_KUMA_URL=https://uptime.example.com
UPTIME_KUMA_USERNAME=keith
UPTIME_KUMA_PASSWORD=...          # dashboard password, or an API key as username/password pair
```

Never commit these. The client redacts secret-bearing fields in every listing it returns.

## CLI (`kuma`)

```bash
export $(grep -v '^#' ~/.kuma.env | xargs)   # or your own sourcing convention

kuma health                                   # connectivity + auth check
kuma monitors list --json                     # all monitors (normalized)
kuma monitors find --query sea --json         # substring/fnmatch on name+tags
kuma heartbeats --monitor-id 25 --json        # recent beats for one monitor
kuma incident-context --monitor "SEA SSH"     # composite incident brief
kuma notifications list --json                # redacted notification configs
kuma maintenance list --json

# operator-gated mutations (require --yes; dry-run by default)
kuma bulk-update --name-pattern 'mseast*' \
    --updates '{"maxretries": 2}' --dry-run
kuma bulk-update --name-pattern 'mseast*' \
    --updates '{"maxretries": 2}' --yes
kuma set-notifications --name-pattern 'ms*' --notification-ids 2,3 --dry-run
kuma monitor pause --id 25 --yes
```

Exit codes: `0` ok · `1` error · `2` usage · `3` connection · `4` auth · `5` timeout.

### Kuma v2 editing notes (learned the hard way)

- `editMonitor` is a **full replace**, not a patch. The CLI's mutating verbs send
  the complete live object with fields applied — never hand-craft bare payloads.
- `notificationIDList` must be a map (`{"2": true}`), not an array.

## MCP server (read-only)

Exposes 7 tools to any MCP client: `health`, `list_monitors`, `find_monitors`,
`get_heartbeats`, `list_notifications`, `list_maintenance`,
`kuma_incident_context`. No mutation tools are registered.

Hermes config example:

```yaml
mcp_servers:
  kuma:
    command: /path/to/uptime-kuma-rest-api/bin/kuma-mcp-wrapper   # sources env, then execs kuma-mcp
    connect_timeout: 30
    timeout: 60
```

## REST adapter (optional)

```bash
python -m uptime_kuma.api_server            # 127.0.0.1:5001
curl 'http://127.0.0.1:5001/incident-context?monitor=SEA%20SSH&lookback_minutes=60'
curl http://127.0.0.1:5001/health
```

## Development

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest -q               # 88 tests, offline (fake transport)
uvx ruff check uptime_kuma tests bin
```

Design notes: [`docs/design-2026-08-25-rewrite.md`](docs/design-2026-08-25-rewrite.md).
