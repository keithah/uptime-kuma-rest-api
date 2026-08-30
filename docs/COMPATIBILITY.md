# Compatibility and upgrade notes

This project speaks to Uptime Kuma through its internal Socket.IO protocol. It is
not a client for a separately versioned public REST API, so Kuma upgrades should
be treated as protocol compatibility changes and verified against a real instance.

> **Rename note (kumactl 3.0.0):** Distribution `uptime-kuma-api` / repo `keithah/uptime-kuma-rest-api` renamed to `keithah/kumactl` (`kumactl` on PyPI). Binaries `kuma`/`kuma-mcp` → `kumactl`/`kumactl-mcp`, wrapper `bin/kuma-mcp-wrapper` → `bin/kumactl-mcp-wrapper`. Python import stays `import uptime_kuma`; env vars stay `UPTIME_KUMA_*` (wrapper prefers `KUMACTL_ENV_FILE` with `KUMA_ENV_FILE` fallback).

## Verified compatibility boundary

| Component | Verified version | Compatibility policy |
|---|---:|---|
| kumactl | 3.0.0 | Current distribution version; binaries `kumactl`/`kumactl-mcp`, import `uptime_kuma` unchanged |
| Uptime Kuma | v2 instance used by live acceptance proof | Verify `health`, monitor inventory, heartbeat reads, notifications, maintenance, and incident context after upgrades |
| Python | 3.13 | Supported by the current test and live MCP environments |
| `python-socketio` | 5.16.4 | Keep within major version 5; reconnect attempts are explicitly bounded by this project |
| `mcp` | 2.1.1 | Keep within major version 2; the adapter uses the stable stdio/server APIs |
| Flask | 3.1.3 | Keep within major version 3 for the optional REST adapter |
| `python-dotenv` | 1.2.3 | Keep within major version 1 |

The exact installed versions above are the versions used for the current live
verification. They are informative; the supported ranges are declared in
`pyproject.toml`.

## Upgrade procedure

1. Run the offline suite: `.venv/bin/python -m pytest -q`.
2. Build the package and inspect the generated metadata: `python -m build`.
3. Against a real Kuma instance, run `kumactl health --json` and a read-only MCP
   initialize plus health call.
4. Exercise monitor, heartbeat, notification, maintenance, and incident-context
   reads. Keep output redacted.
5. Run a bounded soak and compare worker count, CPU, RSS, thread count, and file
   descriptors against the pre-upgrade baseline.
6. Only then promote the dependency or Kuma version.

Do not infer protocol compatibility from a successful TCP or HTTPS connection:
Socket.IO event names, acknowledgement shapes, and streamed collection payloads
must all remain compatible.

## Resource-lifecycle invariant

A long-lived stdio MCP process owns one Kuma client and one Socket.IO transport.
Calls are serialized, failed calls close and discard the client, and reconnect
attempts are bounded. Any upgrade that changes these invariants requires a new
regression test and a fresh soak before release.
