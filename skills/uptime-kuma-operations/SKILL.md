---
name: uptime-kuma-operations
description: "Use when installing, configuring, investigating, or safely mutating Uptime Kuma v2 via the uptime-kuma-api CLI/MCP."
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

Set up the package by following the **Install** section of the repository
README (clone `keithah/uptime-kuma-rest-api`, create an isolated environment,
editable install with dev extras). All setup commands live in the repository,
where they are versioned and reviewed as code.

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

The console scripts live inside the repository's `.venv`. To call `kuma` from any shell, symlink it onto your PATH (for example into `~/.local/bin`):

```sh
mkdir -p "$HOME/.local/bin"
ln -sfn "$PWD/.venv/bin/kuma" "$HOME/.local/bin/kuma"
```

The MCP wrapper execs `<repo>/.venv/bin/kuma-mcp`, so pulling new commits changes what the registered server runs. After updating the checkout, rerun the test suite and the `kuma health --json` smoke test before trusting it.

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

The repository README's **MCP server** section shows the exact wrapper script
and the agent configuration entry; the shipped `bin/kuma-mcp-wrapper` header
documents its behavior. Register the wrapper as a stdio MCP server named
`kuma` (check `hermes mcp add --help` for your build's flags, or use the
documented configuration-file shape). Never pass the credentials through the
server definition's `env` block — that persists them plaintext; the wrapper
exists precisely to keep them out.

Hermes spawns stdio MCP servers with a filtered environment — only `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `SHELL`, `TMPDIR`, and `XDG_*` survive — so exports from your shell profile never reach `kuma-mcp`. Sourcing the protected env file inside the wrapper is mandatory, not optional.

MCP registration has no hot reload: restart the agent, then verify in a NEW session. A saved config entry is not proof of authentication:

- Expected read-only tools: `mcp_kuma_health`, `mcp_kuma_list_monitors`, `mcp_kuma_find_monitors`, `mcp_kuma_get_heartbeats`, `mcp_kuma_list_notifications`, `mcp_kuma_list_maintenance`, `mcp_kuma_kuma_incident_context`.
- Call the health tool once and require `ok: true`.

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
- Save the rollback snapshot OUTSIDE any redaction path (for example `kuma monitors list --json > ~/kuma-snapshots/...`). Listings returned by the CLI/MCP are redacted; a redacted snapshot is fine for diffing but NOT byte-complete for restoring secret-bearing fields. Never replay a redacted snapshot into a live monitor — you would write `***` into real settings.

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
# --name-pattern is a shell-style GLOB (fnmatch), case-insensitive — pass the
# exact monitor name when you mean a single target. Always dry-run first.
.venv/bin/kuma bulk-update --updates '{"maxretries":2}' \
  --name-pattern 'exact-monitor-name' --dry-run
.venv/bin/kuma bulk-update --updates '{"maxretries":2}' \
  --name-pattern 'exact-monitor-name' --yes --json

# Read back and diff: the only changed field must be maxretries.
.venv/bin/kuma monitors get --id <id> --json
```

Alert timing consequence: with `maxretries=N`, the first N failed checks stay pending and paging fires on failure N+1. Lowering maxretries pages earlier.

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
