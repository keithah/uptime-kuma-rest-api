---
name: uptime-kuma-operations
description: "Use when operating Uptime Kuma v2 with the CLI, MCP, or incident runbooks."
version: 1.0.0
author: Keith Anderson
license: MIT
metadata:
  hermes:
    tags: [uptime-kuma, monitoring, incidents, mcp, cli]
    related_skills: [infrastructure-mcp-integration, verification-before-completion]
---

# Uptime Kuma v2 Operations

Use this skill to install, configure, investigate, and safely modify an Uptime Kuma v2 instance through the `uptime-kuma-api` project.

## Installation

Prerequisites:

- Python 3.10+ and `uv`.
- Network access to the Uptime Kuma v2 Socket.IO endpoint.
- An account with permission to read monitors; mutations additionally require operator authorization.
- Hermes only for the optional MCP registration.

Install from the repository:

```sh
git clone https://github.com/keithah/uptime-kuma-rest-api.git
cd uptime-kuma-rest-api
uv venv
uv pip install -e '.[dev]'
```

Configure credentials without putting them in the repository, shell history, logs, or chat:

```sh
umask 077
cat > "$HOME/.kuma.env" <<'EOF'
UPTIME_KUMA_URL=https://kuma.example.com
UPTIME_KUMA_USERNAME=your_username
UPTIME_KUMA_PASSWORD=replace_me
EOF
. "$HOME/.kuma.env"
```

Prefer a password manager's secret injection over a literal password. For 1Password, source a protected file generated from `op read`, and verify its permissions are `0600`; never print the values.

Verify the installation before configuring MCP:

```sh
.venv/bin/kuma health --json
```

A successful response has `ok: true` and `authenticated: true`. If it fails, classify the error as configuration, authentication, connectivity, or timeout before changing anything.

## Optional Hermes MCP registration

The MCP adapter is read-only. Mutations stay in the explicitly operator-gated CLI.

Create a wrapper so Hermes does not depend on filtered parent-process environment variables:

```sh
#!/bin/sh
set -eu
umask 077
ENV_FILE=${KUMA_ENV_FILE:-$HOME/.kuma.env}
[ -r "$ENV_FILE" ] || { printf '%s\n' "Unreadable KUMA_ENV_FILE" >&2; exit 78; }
set -a
. "$ENV_FILE"
set +a
exec /absolute/path/to/uptime-kuma-rest-api/.venv/bin/kuma-mcp
```

Make it executable, then register the command using the Hermes MCP configuration mechanism available on the target installation. The equivalent native entry is:

```yaml
mcp_servers:
  kuma:
    command: /absolute/path/to/kuma-mcp-wrapper
    connect_timeout: 30
    timeout: 60
```

Restart or start a new Hermes session as required for MCP configuration changes. Verify the server itself and then the registered tools; a saved config entry is not proof of authentication:

```sh
.venv/bin/kuma-mcp   # protocol process; use the Hermes MCP test command for connectivity
hermes mcp test kuma
```

Expected read-only tools are health, monitor listing/search, heartbeats, notifications, maintenance, and incident context.

## Investigation workflow

1. Call the configured `kuma` MCP health tool first.
2. Resolve the monitor by exact name or ID. If uncertain, use monitor search; do not guess IDs from names.
3. Read the monitor summary and recent heartbeats. Use `kuma_incident_context` when a complete timeline, failure rate, average ping, notifications, and maintenance windows are needed.
4. Check maintenance windows before declaring an outage.
5. Distinguish `down`, `up`, `pending`, `maintenance`, `unknown`, stale data, and a real outage. Pending failures can be retries rather than a page-worthy incident.
6. Keep investigation output redacted. Notification configs, URLs containing `user:password@`, bearer tokens, webhook URLs, TLS material, and database connection strings must not be copied into reports.
7. Report evidence, timestamps, affected monitor, likely cause, and the next safe action. Do not claim resolution from a successful API call alone; read the target back.

When the MCP server is unavailable, use the CLI against the same environment. Direct SSH/SQLite inspection is a last resort and must not involve copying a large live Kuma database.

## Safe monitor changes

Before any mutation:

- Confirm the target by numeric ID and exact name.
- Read the full current monitor object and save a redacted before snapshot outside the repository.
- Confirm the requested field and expected value; show a dry run for bulk operations.
- Prefer one canary monitor, then read it back and compare the changed field.
- For fleet changes, record the selected IDs, apply only after explicit authorization, and verify every result.

Uptime Kuma v2 `editMonitor` is a **full replacement**, not a JSON merge patch. Never send only `{id, maxretries}`. Preserve all required fields from the current object, including accepted status codes and notification mappings. The project client’s `update_monitor()` performs this full-object update and converts notification ID lists to Kuma’s required map shape (`{"2": true}`); use it instead of hand-building Socket.IO payloads.

Mutation examples:

```sh
# Preview targets; no change is made.
.venv/bin/kuma bulk-control pause --group production --dry-run --json

# A destructive operation requires explicit authorization.
.venv/bin/kuma monitor pause --id 43 --yes --json
```

For `maxretries`, use the narrow bulk-update allowlist and verify the result:

```sh
.venv/bin/kuma bulk-update --updates '{"maxretries":2}' --name-pattern 'specific-name' --json
.venv/bin/kuma monitors get --id 43 --json
```

Do not use raw Socket.IO mutation payloads unless the current full object has been retrieved, reviewed, and the server’s v2 schema has been confirmed. Never automate destructive operations from the read-only MCP adapter.

## Troubleshooting

- Missing required variables: source the protected env file and check variable names without printing values.
- Authentication failure: verify the account and Kuma URL; do not put credentials into command arguments.
- Connection failure: verify HTTPS reachability and the Socket.IO path; retry after checking service health.
- Timeout with an otherwise healthy server: Kuma may acknowledge a request and publish the collection asynchronously; retry once and inspect the matching push event.
- MCP tools missing after registration: restart Hermes or start a new session, then run the MCP connectivity test.
- Unexpected monitor update behavior: stop mutations, read the monitor back, and compare the full object. Treat any notification-link loss as urgent and restore from the reviewed before snapshot.

## Completion checklist

- [ ] Package installed in an isolated environment.
- [ ] Credentials supplied through a protected external mechanism.
- [ ] `kuma health --json` returns authenticated success.
- [ ] MCP registration, if requested, passes a real connectivity/tool test.
- [ ] Investigations use monitor IDs, recent heartbeats, maintenance context, and redacted output.
- [ ] Mutations were dry-run, explicitly authorized, full-object safe, and read-back verified.
- [ ] Tests and lint pass before publishing or upgrading the package.
