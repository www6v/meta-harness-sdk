# meta-harness-sdk

> English: [README.md](./README.md)

**[oma-platform](../oma-platform)** 的 Python SDK — Open Managed Agents (OMA) 客户端。

用本包从 Python 调用平台 HTTP API：创建 agent/session、流式事件、挂载 skill/文件、跑 cookbook 工作流，以及访问 OMA 专属资源（evals、dreams、runtimes、integrations 等）。

> **需要先启动 oma-platform**（默认 `http://localhost:8787`）。本仓库是客户端；服务端在 `oma-platform`。

## 特性

- **`OMAClient` / `AsyncOMAClient`** — 同步/异步双客户端，对齐 Anthropic / AsyncAnthropic DX
- **Managed-agents 资源** — agents、sessions、environments、memory stores、vaults（经 Anthropic SDK `base_url`）
- **httpx 资源** — skills、files、dreams、evals、runtimes、integrations、model cards、cost report、me、api_keys、models、session events
- **Cookbook 辅助函数** — `stream_until_end_turn`、`stream_hitl_until_end_turn`、`wait_for_idle_status` 等
- **示例 1–10** — Managed Agents Cookbook 对齐，见 `example/`
- **E2E 测试** — 对真实平台的 pytest 套件（`tests/`）
- **GAIA runner** — 评测脚本，见 `gaia/`（可选）

## 安装

Python **≥ 3.11**。目前仅支持本地安装（尚未发布到 PyPI）。

```bash
cd meta-harness-sdk
uv sync
# 或: pip install -e .
```

## 快速开始

先启动 oma-platform（见 [oma-platform 中文文档](../oma-platform/readme-zh.md)），然后：

```bash
export OMA_API_KEY=dev-key
# 可选: export OMA_PLATFORM_URL=http://localhost:8787
```

```python
from sdk import OMAClient

client = OMAClient()  # 读取 OMA_PLATFORM_URL，否则 http://localhost:8787
agent = client.agents.create(
    name="hello",
    model={"id": "claude-sonnet-4-6"},
)
session = client.sessions.create(agent=agent.id)
```

异步：

```python
from sdk import AsyncOMAClient

async with AsyncOMAClient() as client:
    agent = await client.agents.create(
        name="hello",
        model={"id": "claude-sonnet-4-6"},
    )
```

租户头 / 构造参数（可选）：

```python
client = OMAClient(
    api_key="dev-key",
    tenant_id="your-tenant-id",
    timeout=120.0,
    max_retries=2,
)
```

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `OMA_API_KEY` | 是（或传 `api_key=`） | — | 平台 API Key（`x-api-key`） |
| `OMA_PLATFORM_URL` | 否 | `http://localhost:8787` | 平台 Base URL |
| `OMA_LOG` | 否 | — | `debug` 或 `info` 打开 SDK 日志 |

## 资源一览

| 类型 | 访问方式 | 资源 | 同步 / 异步 |
|------|----------|------|-------------|
| Managed-agents（Anthropic SDK） | `client.agents`、`client.sessions`、… | agents、sessions、environments、memory_stores、vaults | `OMAClient` 同步；`AsyncOMAClient` await |
| Skills / files（httpx，CMA 形状） | `client.skills`、`client.files` | skills（含 versions）、files | 同步为主；`OMAClient` 保留 `*_async` 别名 |
| OMA 专属（httpx） | `client.dreams`、`client.evals`、… | dreams、evals、runtimes、integrations、model_cards、cost_report、me、api_keys、models、events | 双客户端均提供 sync + async |

Session 事件：`client.events`（便利层）；推荐主路径 `client.sessions.events`。Cookbook 流式辅助在 `sdk.cookbook`。

## 示例

Cookbook 启动脚本与夹具说明见 [`example/README.md`](./example/README.md)。

```bash
export OMA_API_KEY=dev-key
uv run python example/example1/data_analyst_agent.py
```

## 测试

需平台（及 harness）已运行：

```bash
export OMA_API_KEY=dev-key
uv run pytest tests/ -x
# 或: ./tests/test.sh
```

## 目录结构

```
meta-harness-sdk/
├── sdk/          # 包：OMAClient、AsyncOMAClient、resources、cookbook
├── example/          # Cookbook 对齐示例 1–10
├── tests/            # E2E pytest
├── gaia/             # GAIA 评测（可选）
├── pyproject.toml
└── SDK-PLAN.md       # 设计 / 覆盖说明
```

## 与 oma-platform 的关系

```
┌────────────────────┐         HTTP + SSE          ┌─────────────────────┐
│  meta-harness-sdk (Python)  │ ──────────────────────────► │  oma-platform :8787 │
│  OMAClient         │                             │  Go 服务 + Console   │
└────────────────────┘                             └──────────┬──────────┘
                                                              │ /internal/turn
                                                              ▼
                                                   ┌─────────────────────┐
                                                   │  oma-harness :8090  │
                                                   │  piPy / FastAPI     │
                                                   └─────────────────────┘
```

- **oma-platform** — 服务端、harness、Console、鉴权
- **meta-harness-sdk** — 面向该平台的 Python 客户端（本仓库）

另见：[`SDK-PLAN.md`](./SDK-PLAN.md)、[`HARNESS_SUPPORT.md`](./HARNESS_SUPPORT.md)。

## 版本

`meta-harness-sdk` **v0.1.0**（`pyproject.toml`）。
