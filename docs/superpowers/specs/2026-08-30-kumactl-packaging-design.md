# kumactl Packaging & Rename — Design

**Date:** 2026-08-30
**Status:** Approved (awaiting spec file review before implementation)
**Repo:** `keithah/uptime-kuma-rest-api` → `keithah/kumactl`
**Distribution:** `kumactl` on PyPI (verified available; `uptime-kuma-api` is owned by `lucasheld/uptime-kuma-api` v1.2.1)
**Binaries:** `kumactl` + `kumactl-mcp` (hard cutover, no `kuma` shim)
**Python import:** `import uptime_kuma` unchanged
**Related:** Printing Press HTTP + name-change PR; prior branch `fix/review-findings-11` (f7e8da6, PR #1)

## 1. Goals

- Publish a standalone PyPI wheel as `kumactl` so Printing Press and any other consumer can `uv add kumactl` / `pip install kumactl` instead of pinning a git URL.
- Fix the PyPI name collision: current `pyproject.toml` declares `uptime-kuma-api` which cannot be uploaded.
- Rename the GitHub repository to `keithah/kumactl` (GitHub retains a redirect from the old name) so GitHub ↔ PyPI ↔ binary names align.
- Ship the native Streamable HTTP transport (`kumactl-mcp --transport streamable-http`) as the shared Hermes default; remove the `kuma` binary names entirely.
- Keep the Python import stable (`uptime_kuma`) to avoid breaking `from uptime_kuma import KumaClient` consumers.
- Update all docs, wrappers, launchd plists, Hermes skill, and compatibility notes in one release.

## 2. Non-Goals

- Renaming the Python import to `kumactl` (deferred; would be a major version of its own).
- Splitting into `kumactl-core` + `kumactl` packages (overkill for ~1.3k LOC).
- Keeping `kuma` / `kuma-mcp` as deprecated aliases.
- Adding a multi-transport supervisor or changing the `stateless_http=False` default (`mcp.run("streamable-http", stateless_http=False)` stays).
- Changing `mcp` SDK pin (`2.1.1`) or Python floor (3.10) in this release.

## 3. Architecture & Components

```
PyPI: kumactl (dist)  ── provides ──►  bin: kumactl, kumactl-mcp
                                          │
Python: import uptime_kuma  ──────────────┘  (package dir unchanged)

uptime_kuma/
  cli.py          → entry: kumactl
  mcp_server.py   → entry: kumactl-mcp  (argparse: --transport {stdio,streamable-http} --host --port --path)
  kuma_client.py / transport.py / redact.py / normalize.py / classify.py / config.py / errors.py / api_server.py

bin/kumactl-mcp-wrapper  → sources $KUMACTL_ENV_FILE (fallback $KUMA_ENV_FILE, then ~/.hermes/kuma.env), execs kumactl-mcp "$@"
launchd: net.hadm.mcp-http.kumactl → kumactl-mcp --transport streamable-http --host 127.0.0.1 --port 40108 --path /mcp
Hermes: hermes mcp add kumactl --url http://127.0.0.1:40108/mcp   (HTTP, not stdio)
Printing Press: uv add kumactl>=3.0.0  (or pinned), generator template emits kumactl-mcp --transport streamable-http
```

## 4. Packaging Changes

### 4.1 pyproject.toml

```toml
[project]
name = "kumactl"                # was "uptime-kuma-api"
version = "3.0.0"               # was "2.1.0" — major bump marks binary/env rename
description = "kumactl — Uptime Kuma CLI + read-only MCP (native Streamable HTTP) — import uptime_kuma"
readme = "README.md"
requires-python = ">=3.10"
# license/authors unchanged
dependencies = [ flask, python-socketio[client], python-dotenv, mcp ]

[project.scripts]
kumactl = "uptime_kuma.cli:main"
kumactl-mcp = "uptime_kuma.mcp_server:main"
# kuma / kuma-mcp removed
```

Rationale for 3.0.0: binary rename (`kuma`→`kumactl`) and wrapper/env-file rename are breaking for shell/Hermes/launchd even though the Python API is stable. If a minor bump is preferred, 2.2.0 is acceptable; spec records 3.0.0 as default and flags the alternative.

### 4.2 Files to Update

- `pyproject.toml` — name, version, scripts, description.
- `README.md` — title, clone URL, `pip install kumactl`, `kumactl health` examples, Hermes config snippet, skill install URL (`raw.githubusercontent.com/keithah/kumactl/...`), REST adapter docs.
- `bin/kuma-mcp-wrapper` → `bin/kumactl-mcp-wrapper` — rename, update help text, env resolution order: `${KUMACTL_ENV_FILE:-${KUMA_ENV_FILE:-$HOME/.hermes/kuma.env}}`, still honors `KUMA_ENV_FILE` for one-release backward compat, `umask 077` preserved.
- `skills/uptime-kuma-operations/SKILL.md` — wrapper path, binary names, install URL.
- `docs/design-2026-08-25-rewrite.md` — transport diagram, binary names, repo path.
- `docs/COMPATIBILITY.md` — version table (mcp 2.1.1, etc.) plus rename/upgrade notes.
- `docs/superpowers/specs/*` — this spec (new).
- Any `Makefile` / CI / `uv.lock` / `.gitignore` references to `kuma` binary by name (search repo-wide to confirm).

No change to `uptime_kuma/` package directory name or `import` statements.

## 5. Repository Rename

- GitHub: Settings → Rename `uptime-kuma-rest-api` → `kumactl`. GitHub creates a redirect; old clone URLs continue to work for an extended period.
- Local remotes:

  ```bash
  git remote set-url origin https://github.com/keithah/kumactl.git
  # or git@github.com:keithah/kumactl.git for SSH
  git remote set-url --push origin https://github.com/keithah/kumactl.git
  ```
- Re-clone not required; verify with `git ls-remote`.
- Tags/releases: `2.1.0` tag stays on old commit; new `3.0.0` tag cut from this PR's merge commit.
- Branch `fix/review-findings-11` will be rebased onto the rename commit or merged first (order TBD; spec recommends rename PR merges before or squashed with findings PR to avoid a double rename diff).

## 6. Configuration & Environment

- Env vars: `UPTIME_KUMA_URL`, `UPTIME_KUMA_USERNAME`, `UPTIME_KUMA_PASSWORD`, `UPTIME_KUMA_SOCKET_PATH`, `UPTIME_KUMA_TIMEOUT`, `UPTIME_KUMA_TRANSPORT_WAIT` **unchanged**. No `KUMACTL_*` aliases in this release (defer to avoid churn; add later if desired).
- Env file: canonical remains `~/.hermes/kuma.env` (mode 0600) for this release to avoid breaking existing Hermes host. Wrapper checks `KUMACTL_ENV_FILE` first, then `KUMA_ENV_FILE`, then the default. A future release may canonicalise to `~/.hermes/kumactl.env` with a migration note; not in scope now.
- `Config.from_env()` continues to load `UPTIME_KUMA_*` (already hardened to validate `UPTIME_KUMA_TIMEOUT` / `TRANSPORT_WAIT` as floats).

## 7. Hermes & Launchd Migration (host `mbpdev.gate-sailfin` / `hermes`)

1. Build & verify wheel (see §9).
2. `launchctl bootout gui/$(id -u)/net.hadm.mcp-http.kuma` ; remove old plist `net.hadm.mcp-http.kuma.plist`.
3. Install new plist `net.hadm.mcp-http.kumactl.plist`:

   ```
   Label: net.hadm.mcp-http.kumactl
   ProgramArguments: /Users/hermes/src/kumactl/bin/kumactl-mcp-wrapper --transport streamable-http --host 127.0.0.1 --port 40108 --path /mcp
   StandardOutPath: /Users/hermes/.hermes/mcp-http/logs/kumactl.out.log
   StandardErrorPath: /Users/hermes/.hermes/mcp-http/logs/kumactl.err.log
   ```
4. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/net.hadm.mcp-http.kumactl.plist` ; verify `launchctl print` shows `state = running`, single PID, `runs = 1`.
5. Hermes MCP registry: remove old stdio/URL entry if present, `hermes mcp add kumactl --url http://127.0.0.1:40108/mcp` (or config edit), then `hermes mcp test kumactl` → 7 tools (`health`, `list_monitors`, `find_monitors`, `get_heartbeats`, `list_notifications`, `list_maintenance`, `kuma_incident_context`).
6. Verify `ps -o command | grep kumactl-mcp` shows one process, no Supergateway.
7. Keep `~/.hermes/kuma.env` perms 0600; do not commit or print.

Rollback: re-enable old `net.hadm.mcp-http.kuma` plist and revert `hermes mcp add` if new service fails to start; old repo URL still resolves via redirect.

## 8. Printing Press Integration (separate PR)

- Dependency: `uptime-kuma-rest-api @ git+https://github.com/keithah/uptime-kuma-rest-api` → `kumactl>=3.0.0` (or `==3.0.0` pin per PP convention). Update `pyproject.toml` / `uv.lock` / `requirements` accordingly.
- Generator / templates / skills that shell out to `kuma` or `kuma-mcp` → `kumactl` / `kumactl-mcp --transport streamable-http --host … --port … --path /mcp`.
- Any docs or `bin/` shims referencing `kuma` wrapper → `kumactl-mcp-wrapper`.
- Verify PP's `uv sync` + `pytest` / generator tests pass with new wheel; no `printing-press` release artifacts hand-built (use official generator).
- Spec does not change PP's product logic; only the dependency + command names + transport flags.

## 9. Testing & Verification

- Wheel: `uv build && twine check dist/*` (or `uvx twine check`), then `pip install dist/kumactl-3.0.0-py3-none-any.whl` in a clean venv:
  - `kumactl --help`, `kumactl health --json` (with `KUMA_ENV_FILE`), `kumactl-mcp --help`, `kumactl-mcp --transport streamable-http --help`.
  - Live MCP: `curl` + `kumactl-mcp --transport streamable-http` smoke, then `hermes mcp test kumactl`.
- Offline gate: `.venv/bin/pytest -q` (102 passed expected), `compileall`, `ruff check` clean, `git diff --check`.
- PyPI: `uv publish` / `twine upload` under `keithah` (name already confirmed available). Verify `pip install kumactl` from public index resolves the new version.
- Post-rename: `git ls-remote https://github.com/keithah/kumactl.git`, old URL redirect test, skill install URL fetch.

## 10. Rollout Order

1. Land `fix/review-findings-11` (or rebase it onto rename commit) — whichever merges first updates `main`.
2. This spec's implementation PR: rename dist/bin/wrapper/docs + `3.0.0` bump + `README`/`COMPATIBILITY`/`SKILL` updates.
3. Rename GitHub repo (`uptime-kuma-rest-api` → `kumactl`) and update local remotes.
4. Publish `kumactl 3.0.0` to PyPI; tag `v3.0.0`.
5. Host migration (launchd + Hermes) on `mbpdev` / Hermes fleet.
6. Printing Press PR (dependency + transport + name change).
7. Announce / archive old `kuma` binary name in CHANGELOG/notes.

## 11. Risks & Mitigations

- **Shadowing `kumactl` on PyPI** — already verified free; claim immediately after merge to avoid squatting.
- **Existing shell aliases / scripts calling `kuma`** — no shim by design; document breaking change in CHANGELOG and provide one-liner to update (`sed -i s/kuma/kumactl/g` + `kuma-mcp` → `kumactl-mcp`).
- **Env var churn** — mitigated by keeping `UPTIME_KUMA_*` names and supporting both `KUMACTL_ENV_FILE` and `KUMA_ENV_FILE` in wrapper.
- **Old git remotes** — mitigated by GitHub redirect + explicit `git remote set-url` step in migration guide.

## 12. Decisions Recorded

| Decision | Choice | Rationale |
|---|---|---|
| Distribution name | `kumactl` (A) | Matches binary, shortest, available; B keeps repo alignment but is longer, C is mouthful |
| Binary names | `kumactl` / `kumactl-mcp` (B, hard cut) | No `kuma` shim; one-time churn |
| Import | `uptime_kuma` (A) | Zero breaking change for `from uptime_kuma import` |
| Repo name | `keithah/kumactl` | Aligns with dist/binary; redirect preserves old clones |
| Version | `3.0.0` | Major bump for binary/paths breaking change (2.2.0 acceptable alternative) |
| Env file | `~/.hermes/kuma.env` canonical this release | Avoid host break; wrapper checks both `KUMACTL_ENV_FILE` and `KUMA_ENV_FILE` |
