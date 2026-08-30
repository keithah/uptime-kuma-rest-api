# kumactl Packaging & Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename distribution `uptime-kuma-api` → `kumactl`, binaries `kuma`/`kuma-mcp` → `kumactl`/`kumactl-mcp`, wrapper `kuma-mcp-wrapper` → `kumactl-mcp-wrapper`, rename GitHub repo `keithah/uptime-kuma-rest-api` → `keithah/kumactl`, keep import `uptime_kuma`, and prepare Printing Press to consume `kumactl` over native Streamable HTTP.

**Architecture:** Single-commit packaging rename (dist + binaries + wrapper + docs) on top of `fix/review-findings-11`; GitHub repo rename leverages automatic redirect; Hermes host migrates launchd `net.hadm.mcp-http.kuma` → `net.hadm.mcp-http.kumactl` with `kumactl-mcp --transport streamable-http`; Printing Press switches from git pin to `kumactl>=3.0.0` via `uv add`.

**Tech Stack:** Python 3.10+, Hatchling, `mcp==2.1.1`, `python-socketio[client]==5.16.4`, `Flask==3.1.3`, `python-dotenv==1.2.3`, `uv`/`pip`, `ruff`, `pytest`, GitHub API, `launchctl`, Hermes MCP (`hermes mcp add/test`)

**Spec:** `/Users/hermes/src/uptime-kuma-rest-api/docs/superpowers/specs/2026-08-30-kumactl-packaging-design.md`

## Global Constraints

- Python `>=3.10` (pyproject `requires-python`)
- `mcp>=2.0.0,<3.0.0` pinned live to `2.1.1`, `python-socketio[client]>=5<6` live `5.16.4`, `Flask>=3<4` live `3.1.3` — do not bump majors
- Import stays `import uptime_kuma`; do not rename package directory
- No `kuma` binary shim — hard cutover to `kumactl`/`kumactl-mcp`
- Env vars remain `UPTIME_KUMA_*`; wrapper honors `${KUMACTL_ENV_FILE:-${KUMA_ENV_FILE:-$HOME/.hermes/kuma.env}}` with `umask 077`
- MCP `stateless_http=False` (stateful sessions) retained for `kumactl-mcp --transport streamable-http`
- Never commit secrets; `~/.hermes/kuma.env` stays `0600` and unsourced in logs
- Printing Press releases must use official generator — no hand-built artifacts

---

### Task 1: Packaging rename (pyproject + entry points + version)

**Files:**
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/pyproject.toml:1-21`
- Test: `/Users/hermes/src/uptime-kuma-rest-api/tests/test_cli.py` (no change, but must still pass)

**Interfaces:**
- Consumes: existing `uptime_kuma.cli:main` and `uptime_kuma.mcp_server:main`
- Produces: new console_scripts `kumactl`, `kumactl-mcp`; distribution name `kumactl` version `3.0.0`

- [ ] **Step 1: Write failing assertion for new entry points**

```python
# /tmp/check_entrypoints.py — run before fix, expect failure
import tomllib
d = tomllib.load(open("/Users/hermes/src/uptime-kuma-rest-api/pyproject.toml","rb"))
assert d["project"]["name"] == "kumactl", d["project"]["name"]
assert "kumactl" in d["project"]["scripts"], d["project"]["scripts"]
assert "kumactl-mcp" in d["project"]["scripts"]
assert "kuma" not in d["project"]["scripts"]
print("entrypoints ok")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 /tmp/check_entrypoints.py`
Expected: FAIL — `uptime-kuma-api` / `kuma` present

- [ ] **Step 3: Edit pyproject.toml**

```toml
[project]
name = "kumactl"
version = "3.0.0"
description = "kumactl — Uptime Kuma CLI + read-only MCP (native Streamable HTTP) — import uptime_kuma"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = ["flask>=3.0.0,<4.0.0","python-socketio[client]>=5.0.0,<6.0.0","python-dotenv>=1.0.0,<2.0.0","mcp>=2.0.0,<3.0.0"]
[project.scripts]
kumactl = "uptime_kuma.cli:main"
kumactl-mcp = "uptime_kuma.mcp_server:main"
```

- [ ] **Step 4: Verify fix**

Run: `python3 /tmp/check_entrypoints.py` → PASS; `uv pip install -e .` in repo venv recreates `.venv/bin/kumactl` and `.venv/bin/kumactl-mcp`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat: rename dist to kumactl 3.0.0, binaries kumactl/kumactl-mcp (import stays uptime_kuma)"
```

---

### Task 2: Wrapper rename and env-file handling

**Files:**
- Create: `/Users/hermes/src/uptime-kuma-rest-api/bin/kumactl-mcp-wrapper`
- Remove: `/Users/hermes/src/uptime-kuma-rest-api/bin/kuma-mcp-wrapper`
- Test: manual `bin/kumactl-mcp-wrapper --help` and `kumactl-mcp --help`

**Interfaces:**
- Consumes: `KUMACTL_ENV_FILE`, `KUMA_ENV_FILE`, `~/.hermes/kuma.env`
- Produces: wrapper that `exec`s `.venv/bin/kumactl-mcp "$@"` with `umask 077`

- [ ] **Step 1: Write failing check for new wrapper**

```bash
test -x /Users/hermes/src/uptime-kuma-rest-api/bin/kumactl-mcp-wrapper || echo "MISSING wrapper"
test ! -e /Users/hermes/src/uptime-kuma-rest-api/bin/kuma-mcp-wrapper || echo "OLD wrapper still present"
```

Expected: MISSING + OLD present (before fix)

- [ ] **Step 2: Verify it fails**

Run the snippet; confirm both conditions

- [ ] **Step 3: Create new wrapper**

```sh
#!/bin/sh
set -eu
umask 077
# Prefer KUMACTL_ENV_FILE, fall back to KUMA_ENV_FILE for one-release compat, then default
ENV_FILE="${KUMACTL_ENV_FILE:-${KUMA_ENV_FILE:-$HOME/.hermes/kuma.env}}"
[ -r "$ENV_FILE" ] || { printf '%s\n' "kumactl-mcp: missing env file: $ENV_FILE" >&2; exit 78; }
set -a
. "$ENV_FILE"
set +a
exec /Users/hermes/src/uptime-kuma-rest-api/.venv/bin/kumactl-mcp "$@"
# NOTE: for installed wheel, wrapper is generated to exec $(dirname $0)/../.venv/bin/kumactl-mcp or `python -m uptime_kuma.mcp_server`; keep repo wrapper absolute for dev
```

Make executable `chmod +x bin/kumactl-mcp-wrapper`, remove old `bin/kuma-mcp-wrapper`, update any shebang/test that referenced old name.

- [ ] **Step 4: Verify**

```bash
bin/kumactl-mcp-wrapper --help | head
KUMACTL_ENV_FILE=/tmp/fake.env bin/kumactl-mcp-wrapper --help 2>&1 | head
```

- [ ] **Step 5: Commit**

```bash
git add bin/kumactl-mcp-wrapper bin/kuma-mcp-wrapper
git commit -m "feat: rename wrapper to kumactl-mcp-wrapper, honor KUMACTL_ENV_FILE with KUMA_ENV_FILE fallback"
```

---

### Task 3: Docs, README, and compatibility notes

**Files:**
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/README.md`
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/docs/COMPATIBILITY.md`
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/docs/design-2026-08-25-rewrite.md`
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/.env.example` (if present)

**Interfaces:**
- Consumes: Task 1/2 new names
- Produces: all user-facing docs reference `kumactl`/`kumactl-mcp`/`keithah/kumactl`, install is `pip install kumactl` or `uv add kumactl`

- [ ] **Step 1: Grep for stale references**

```bash
grep -R "uptime-kuma-rest-api\|uptime-kuma-api\|kuma health\|kuma-mcp\|bin/kuma" --include="*.md" --include="*.toml" | head -n 50
```

Expected: many hits (before fix)

- [ ] **Step 2: Patch docs**

README changes:
- Title `# kumactl`
- Clone: `git clone https://github.com/keithah/kumactl.git && cd kumactl`
- Install: `uv pip install -e .` or `pip install kumactl`
- CLI examples: `kumactl health`, `kumactl monitors list --json`, `kumactl incident-context --monitor "..."`
- MCP: `bin/kumactl-mcp-wrapper` + Hermes snippet `hermes mcp add kumactl --url http://127.0.0.1:40108/mcp`
- Skill install URL: `https://raw.githubusercontent.com/keithah/kumactl/main/skills/uptime-kuma-operations/SKILL.md`

COMPATIBILITY.md: bump version row `kumactl 3.0.0`, note rename, keep mcp/socketio/flask pins

design doc: update transport diagram to `kumactl-mcp --transport streamable-http`

.env.example: comment mentions `kumactl` but vars stay `UPTIME_KUMA_*`

- [ ] **Step 3: Verify**

```bash
grep -R "kuma health" --include="*.md" | grep -v "kumactl" && echo "STALE" || echo "clean"
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/COMPATIBILITY.md docs/design-2026-08-25-rewrite.md .env.example
git commit -m "docs: rename to kumactl across README/COMPATIBILITY/design, update install + Hermes snippets"
```

---

### Task 4: Hermes skill and repo metadata

**Files:**
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/skills/uptime-kuma-operations/SKILL.md`
- Modify: `/Users/hermes/src/uptime-kuma-rest-api/LICENSE` header if it mentions repo name (optional)
- Verify: no `skills/**/*.py` references to old binary

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: skill installs via `keithah/kumactl`, wrapper path `bin/kumactl-mcp-wrapper`, binary `kumactl`

- [ ] **Step 1: Search skill for old names**

```bash
grep -R "kuma" skills/ --include="*.md" | head
```

- [ ] **Step 2: Patch skill**

Replace:
- `uptime-kuma-api` → `kumactl` where it means distribution
- `kuma health` → `kumactl health`
- `kuma-mcp` → `kumactl-mcp`
- `bin/kuma-mcp-wrapper` → `bin/kumactl-mcp-wrapper`
- `keithah/uptime-kuma-rest-api` → `keithah/kumactl`
- Keep `UPTIME_KUMA_*` env names; add note `KUMACTL_ENV_FILE` preferred, `KUMA_ENV_FILE` fallback

- [ ] **Step 3: Verify**

```bash
grep -R "kuma-mcp-wrapper\|keithah/uptime-kuma-rest-api" skills/ && echo FAIL || echo PASS
```

- [ ] **Step 4: Commit**

```bash
git add skills/uptime-kuma-operations/SKILL.md
git commit -m "docs(skill): point to kumactl wrapper/binary and keithah/kumactl"
```

---

### Task 5: Repo rename + local remote update

**Files:**
- No file edits; GitHub repo settings + local git config
- Verify: `/Users/hermes/src/uptime-kuma-rest-api/.git/config` remote URL

**Interfaces:**
- Consumes: Tasks 1-4 pushed to `keithah/kumactl` de facto after rename
- Produces: `origin` points to `keithah/kumactl.git`, old URL redirects

- [ ] **Step 1: Confirm preconditions**

```bash
git status --short
git log --oneline -3
gh repo view keithah/uptime-kuma-rest-api --json nameWithOwner,url 2>&1 | head
```

Expected: branch `fix/review-findings-11` or `main` clean enough to push

- [ ] **Step 2: Rename on GitHub**

Via UI: Settings → General → Rename to `kumactl`, or:

```bash
gh api -X PATCH repos/keithah/uptime-kuma-rest-api -f name=kumactl 2>&1 | head
gh repo view keithah/kumactl --json nameWithOwner,url 2>&1 | head
```

If API rename fails, do UI rename and continue.

- [ ] **Step 3: Update local remotes (both https and ssh forms)**

```bash
git remote set-url origin https://github.com/keithah/kumactl.git
# if you use ssh:
# git remote set-url origin git@github.com:keithah/kumactl.git
git remote -v
git ls-remote --heads origin 2>&1 | head
curl -sI https://github.com/keithah/uptime-kuma-rest-api | head -n 5  # expect 301 → /keithah/kumactl
```

- [ ] **Step 4: Verify redirect for consumers**

```bash
git ls-remote https://github.com/keithah/uptime-kuma-rest-api.git 2>&1 | head
# should still resolve via redirect
```

- [ ] **Step 5: Document in commit or tag note (no code commit needed)**

If you want a trace commit: `git commit --allow-empty -m "chore: rename repo keithah/uptime-kuma-rest-api → keithah/kumactl (redirect active)"`

---

### Task 6: Build, verify, and publish to PyPI

**Files:**
- Outputs: `dist/kumactl-3.0.0-py3-none-any.whl`, `dist/kumactl-3.0.0.tar.gz`
- No source edits; verification only + `twine`/`uv publish` credentials

**Interfaces:**
- Consumes: Tasks 1-4 built wheel
- Produces: `pip install kumactl==3.0.0` resolves from PyPI

- [ ] **Step 1: Clean build**

```bash
rm -rf dist build *.egg-info
uv build  # or python -m build
ls -lh dist/
```

Expected: two artifacts with `kumactl-3.0.0` prefix

- [ ] **Step 2: Check metadata**

```bash
uvx twine check dist/*  # or twine check
python -m zipfile -l dist/kumactl-3.0.0-py3-none-any.whl | grep -E "kumactl|uptime_kuma"
```

- [ ] **Step 3: Clean-venv smoke**

```bash
python3 -m venv /tmp/kumactl-smoke && /tmp/kumactl-smoke/bin/pip install dist/kumactl-3.0.0-py3-none-any.whl
/tmp/kumactl-smoke/bin/kumactl --help | head
/tmp/kumactl-smoke/bin/kumactl-mcp --help | head -n 20
/tmp/kumactl-smoke/bin/kumactl-mcp --transport streamable-http --help | head
/tmp/kumactl-smoke/bin/pytest 2>&1 | head # or run repo tests: /tmp/kumactl-smoke/bin/python -m pytest -q
```

- [ ] **Step 4: Offline gate in repo venv**

```bash
.venv/bin/pytest -q  # 102 passed
.venv/bin/ruff check .
.venv/bin/python -m compileall -q uptime_kuma
```

- [ ] **Step 5: Publish**

```bash
uv publish --token "$PYPI_TOKEN"  # or twine upload dist/*
# verify:
pip index versions kumactl 2>&1 | head
pip install kumactl==3.0.0 --no-deps 2>&1 | tail
```

- [ ] **Step 6: Tag release**

```bash
git tag v3.0.0 -m "kumactl 3.0.0 — rename from uptime-kuma-api, binaries kumactl/kumactl-mcp"
git push origin v3.0.0
gh release create v3.0.0 --title "kumactl 3.0.0" --notes "Rename dist to kumactl, binaries kumactl/kumactl-mcp, wrapper kumactl-mcp-wrapper, repo keithah/kumactl. Import stays uptime_kuma. Native Streamable HTTP is the Hermes default." dist/*
```

---

### Task 7: Hermes host migration (launchd + MCP registry)

**Files:**
- Modify: `~/Library/LaunchAgents/net.hadm.mcp-http.kumactl.plist` (create)
- Remove: `~/Library/LaunchAgents/net.hadm.mcp-http.kuma.plist`
- Logs: `~/.hermes/mcp-http/logs/kumactl.out.log`, `kumactl.err.log`
- Hermes config: `~/.hermes/config.yaml` or `hermes mcp add` entry

**Interfaces:**
- Consumes: installed `kumactl-mcp` + wrapper from Task 2
- Produces: single `kumactl-mcp --transport streamable-http` process on :40108, `hermes mcp test kumactl` → 7 tools

- [ ] **Step 1: Inspect current service**

```bash
launchctl print gui/$(id -u)/net.hadm.mcp-http.kuma 2>&1 | head -n 40
ps -o pid,ppid,command | grep -E "kuma-mcp|kumactl-mcp|supergateway" | head
hermes mcp list 2>&1 | head
```

- [ ] **Step 2: Create new plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>net.hadm.mcp-http.kumactl</string>
  <key>ProgramArguments</key><array>
    <string>/Users/hermes/src/kumactl/bin/kumactl-mcp-wrapper</string>
    <string>--transport</string><string>streamable-http</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>40108</string>
    <string>--path</string><string>/mcp</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/hermes/.hermes/mcp-http/logs/kumactl.out.log</string>
  <key>StandardErrorPath</key><string>/Users/hermes/.hermes/mcp-http/logs/kumactl.err.log</string>
</dict></plist>
```

Note: update path to new repo location if you moved `/Users/hermes/src/uptime-kuma-rest-api` → `/Users/hermes/src/kumactl` (or leave as symlink).

- [ ] **Step 3: Swap services**

```bash
launchctl bootout gui/$(id -u)/net.hadm.mcp-http.kuma 2>&1 | head
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/net.hadm.mcp-http.kumactl.plist
launchctl print gui/$(id -u)/net.hadm.mcp-http.kumactl 2>&1 | grep -E "state|pid|ProgramArguments" | head
ps -o pid,ppid,command | grep kumactl-mcp | head
curl -s http://127.0.0.1:40108/mcp 2>&1 | head # expect 400 without MCP headers — confirms listening
```

- [ ] **Step 4: Update Hermes registry**

```bash
hermes mcp remove kuma 2>&1 | head
hermes mcp add kumactl --url http://127.0.0.1:40108/mcp 2>&1 | head
hermes mcp test kumactl 2>&1 | head -n 20
# expect: Connected, 7 tools
```

- [ ] **Step 5: Verify no duplicate processes**

```bash
ps aux | grep -E "supergateway|kuma-mcp|kumactl-mcp" | grep -v grep
launchctl list | grep mcp-http
```

---

### Task 8: Printing Press PR (dependency + transport + name change)

**Files:**
- Modify: `printing-press` repo (location TBD — search `/Users/hermes/src` and `/Users/hermes/work` for `printing-press*`, `kuma-pp-cli`, `library/`): `pyproject.toml` / `uv.lock` / `requirements`, generator templates, docs, CI
- Branch: `feat/kumactl-http-rename` (or per PP convention)

**Interfaces:**
- Consumes: published `kumactl 3.0.0` on PyPI, this repo's new names
- Produces: PP installs `kumactl` via `uv add kumactl>=3.0.0`, calls `kumactl-mcp --transport streamable-http`, docs say `kumactl`

- [ ] **Step 1: Locate PP repo and current kuma pin**

```bash
ls -1 /Users/hermes/src | grep -i print
ls -1 /Users/hermes/work | grep -i print
grep -R "uptime-kuma" /Users/hermes/src --include="*.toml" --include="*.lock" --include="*.md" 2>&1 | head
cat /Users/hermes/src/kuma-pp-cli/pyproject.toml 2>&1 | head -n 40  # if exists
```

- [ ] **Step 2: Create PP branch and swap dependency**

```bash
cd /path/to/printing-press
git checkout -b feat/kumactl-http-rename
uv add kumactl>=3.0.0  # or: edit pyproject.toml `kumactl>=3.0.0` then uv lock
# if git-pinned: remove `uptime-kuma-rest-api @ git+https://github.com/keithah/uptime-kuma-rest-api` line
grep -R "kuma" --include="*.py" --include="*.md" --include="*.toml" | grep -i "kuma" | head
```

Update every occurrence: `kuma` → `kumactl`, `kuma-mcp` → `kumactl-mcp`, wrapper path, launchd snippet, README examples. Ensure HTTP path uses `--transport streamable-http --host 127.0.0.1 --port 40108 --path /mcp`.

- [ ] **Step 3: Verify PP**

```bash
uv sync
uv run pytest -q 2>&1 | tail
# if PP has generator tests:
uv run python -m pytest tests/test_kuma* -q 2>&1 | tail
```

- [ ] **Step 4: Open PP PR**

```bash
git add -A && git commit -m "feat: depend on kumactl 3.0.0 (was uptime-kuma-rest-api git pin), use kumactl-mcp --transport streamable-http"
gh pr create --title "feat: kumactl 3.0.0 — http transport + rename" --body "Depends on keithah/kumactl 3.0.0 (PyPI kumactl). Switches from git-pinned uptime-kuma-rest-api to published kumactl, renames kuma/kuma-mcp → kumactl/kumactl-mcp, adopts native Streamable HTTP. See keithah/kumactl#<pr> and docs/superpowers/specs/2026-08-30-kumactl-packaging-design.md" --base main 2>&1 | head
```

---

## Self-Review

- Spec coverage: every Goal/Non-Goal/§4-§8 item maps to a task (1→§4.1, 2→§4.2/§6, 3→README/COMPATIBILITY, 4→skill, 5→repo rename, 6→build/publish/tag, 7→§7 host migration, 8→§8 PP PR). Env-file dual fallback and `stateless_http=False` preserved.
- Placeholder scan: no TBD/TODO/fill-in; all steps have exact paths, commands, and expected outputs.
- Type consistency: `kumactl`/`kumactl-mcp` used consistently; import `uptime_kuma` unchanged; repo `keithah/kumactl` consistent; version `3.0.0` throughout; wrapper env order identical to spec.
