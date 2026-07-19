# oma-sdk

> 中文文档：[readme-zh.md](./readme-zh.md)

Python SDK for **[oma-platform](../oma-platform)** — the Open Managed Agents (OMA) stack.

Use this package to call the platform HTTP API from Python: create agents/sessions, stream events, mount skills/files, drive cookbook-style workflows, and exercise OMA-only resources (evals, dreams, runtimes, integrations, …).

> **Requires a running oma-platform** (default `http://localhost:8787`). This repo is the client; the server lives in `oma-platform`.

## Features

- **`OMAClient`** — single entrypoint over Anthropic SDK (`base_url`) + `httpx`
- **Managed-agents resources** — agents, sessions, environments, memory stores, vaults, skills
- **OMA-only resources** — dreams, evals, runtimes, integrations, model cards, cost report, me, api_keys, files, models, session events
- **Cookbook helpers** — `stream_until_end_turn`, `stream_hitl_until_end_turn`, `wait_for_idle_status`, …
- **Examples 1–10** — Managed Agents Cookbook parity under `example/`
- **E2E tests** — pytest suite against a live platform (`tests/`)
- **GAIA runner** — evaluation harness under `gaia/` (optional)

## Install

Python **≥ 3.11**. Local install only (not published to PyPI yet).

```bash
cd oma-sdk
uv sync
# or: pip install -e .
```

## Quick start

Start oma-platform first (see [oma-platform README](../oma-platform/README.md)), then:

```bash
export OMA_API_KEY=dev-key
# optional: export OMA_PLATFORM_URL=http://localhost:8787
```

```python
from oma_sdk import OMAClient

client = OMAClient()  # OMA_PLATFORM_URL or http://localhost:8787
agent = client.agents.create(
    name="hello",
    model={"id": "claude-sonnet-4-6"},
)
session = client.sessions.create(agent=agent.id)
```

Tenant header (optional):

```python
client = OMAClient(tenant_id="your-tenant-id")
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OMA_API_KEY` | yes | — | Platform API key (`x-api-key`) |
| `OMA_PLATFORM_URL` | no | `http://localhost:8787` | Platform base URL |

## Resource map

| Kind | Access | Resources |
|------|--------|-----------|
| Managed-agents (Anthropic SDK) | `client.agents`, `client.sessions`, … | agents, sessions, environments, memory_stores, vaults, skills |
| OMA-only (`httpx`) | `client.dreams`, `client.evals`, … | dreams, evals, runtimes, integrations, model_cards, cost_report, me, api_keys, files, models, events |

Session event helpers: `client.events` (`send` / `list` / `stream`). Cookbook streaming lives in `oma_sdk.cookbook`.

## Examples

Cookbook launchers and fixtures: [`example/README.md`](./example/README.md).

```bash
export OMA_API_KEY=dev-key
uv run python example/example1/data_analyst_agent.py
```

## Tests

With the platform (+ harness) running:

```bash
export OMA_API_KEY=dev-key
uv run pytest tests/ -x
# or: ./tests/test.sh
```

## Layout

```
oma-sdk/
├── oma_sdk/          # package: OMAClient, resources, cookbook, subagent helpers
├── example/          # cookbook parity examples 1–10
├── tests/            # E2E pytest suite
├── gaia/             # GAIA evaluation runner (optional)
├── pyproject.toml
└── SDK-PLAN.md       # design / coverage notes
```

## Relation to oma-platform

```
┌────────────────────┐         HTTP + SSE          ┌─────────────────────┐
│  oma-sdk (Python)  │ ──────────────────────────► │  oma-platform :8787 │
│  OMAClient         │                             │  Go server + Console │
└────────────────────┘                             └──────────┬──────────┘
                                                              │ /internal/turn
                                                              ▼
                                                   ┌─────────────────────┐
                                                   │  oma-harness :8090  │
                                                   │  piPy / FastAPI     │
                                                   └─────────────────────┘
```

- **oma-platform** — server, harness, Console, auth
- **oma-sdk** — Python client for that platform (this repo)

See also: [`SDK-PLAN.md`](./SDK-PLAN.md), [`HARNESS_SUPPORT.md`](./HARNESS_SUPPORT.md).

## Version

`oma-sdk` **v0.1.0** (`pyproject.toml`).
