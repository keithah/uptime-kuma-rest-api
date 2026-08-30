# kumactl

Python client + tooling for [Uptime Kuma](https://github.com/louislam/uptime-kuma) v2:
a redacted, typed core client over Socket.IO, an operator CLI, a read-only MCP
server for agent integrations, and an optional Flask REST adapter.

## Install

```bash
git clone https://github.com/keithah/kumactl.git
cd kumactl
uv pip install -e .        # or: pip install kumactl
```

Alternative from PyPI:

```bash
pip install kumactl        # or: uv add kumactl
```

## Configuration

Credentials come from the environment (or `~/.kuma.env`, sourced however you like):

```bash
UPTIME_KUMA_URL=https://uptime.example.com
UPTIME_KUMA_USERNAME=your_username_here
UPTIME_KUMA_PASSWORD=...          # dashboard password, or an API key as username/password pair
```

Never commit these. The client redacts secret-bearing fields in every listing it returns.

## CLI (`kumactl`)

```bash
export $(grep -v '^#' ~/.kuma.env | xargs)   # or your own sourcing convention

kumactl health                                   # connectivity + auth check
kumactl monitors list --json                     # all monitors (normalized)
kumactl monitors find --query sea --json         # substring/fnmatch on name+tags
kumactl heartbeats --monitor-id 25 --json        # recent beats for one monitor
kumactl incident-context --monitor "SEA SSH"     # composite incident brief
kumactl notifications list --json                # redacted notification configs
kumactl maintenance list --json

# operator-gated mutations (require --yes; dry-run by default)
kumactl bulk-update --name-pattern 'mseast*' \
    --updates '{"maxretries": 2}' --dry-run
kumactl bulk-update --name-pattern 'mseast*' \
    --updates '{"maxretries": 2}' --yes
kumactl set-notifications --name-pattern 'ms*' --notification-ids 2,3 --dry-run
kumactl monitor pause --id 25 --yes
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

The wrapper reads credentials from `~/.kuma.env` (or the file named by
`KUMACTL_ENV_FILE`, falling back to `KUMA_ENV_FILE`).

Hermes config example (native Streamable HTTP):

```bash
hermes mcp add kumactl --url http://127.0.0.1:40108/mcp
```

Stdio wrapper example (`hermes mcp add --help` shows the equivalent one-shot command):

```yaml
mcp_servers:
  kumactl:
    command: /path/to/kumactl/bin/kumactl-mcp-wrapper   # sources env, then execs kumactl-mcp
    connect_timeout: 30
    timeout: 60
```

For Streamable HTTP, run `kumactl-mcp --transport streamable-http --host 127.0.0.1 --port 40108 --path /mcp` (via `bin/kumactl-mcp-wrapper`).

## Agent skill

A ready-made operations skill (install, config, incident runbooks, safe
mutations) ships at
[`skills/uptime-kuma-operations/SKILL.md`](skills/uptime-kuma-operations/SKILL.md).
Install it into Hermes with:

```bash
hermes skills install https://raw.githubusercontent.com/keithah/kumactl/main/skills/uptime-kuma-operations/SKILL.md --yes
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
.venv/bin/python -m pytest -q               # offline suite (fake transport)
uvx ruff check uptime_kuma tests bin
```

Design notes: [`docs/design-2026-08-25-rewrite.md`](docs/design-2026-08-25-rewrite.md).

Compatibility boundaries and the upgrade/soak procedure live in
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).
