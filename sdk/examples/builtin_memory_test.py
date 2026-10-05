#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Built-in agent memory — end-to-end test case (Hermes-parity memory).

Exercises the platform built-in memory path (no ``memory_store`` resource):

1. Session 1: ask the agent to remember a preference; the agent calls the
   auto-registered ``memory`` tool (piPy-hermes-memory extension) and the
   platform persists it into the agent-owned store ``agentmem-<agent_id>``.
2. Verify persistence via the internal API
   ``GET /v1/internal/agent_memory?tenant_id=...&agent_id=...``.
3. Session 2 (fresh session, same agent): ask what the user likes; the
   memory snapshot is injected into the system prompt and the agent recalls
   the preference without any tool call.

Prereqs: server + harness run with ``OMA_MEMORY_ENABLED=1``.

Configuration (all via environment variables)::

    OMA_BASE_URL            platform URL   (default http://127.0.0.1:8787)
    OMA_API_KEY             API key        (default dev-key; named keys work)
    OMA_MEMORY_TENANT_ID    tenant for the internal memory check; when unset
                            it is auto-resolved from GET /v1/me
    OMA_MODEL               model id       (default from examples.agents)

Example::

    OMA_API_KEY=oma_xxx OMA_BASE_URL=http://127.0.0.1:8787 \\
        python sdk/examples/builtin_memory_test.py

Named API keys are bound to their own tenant server-side, so resources land
in the console workspace of the key's owner automatically; the global dev
key instead honors the ``x-active-tenant`` header.

The internal secret is read from ``OMA_INTERNAL_SECRET``, falling back to
the sibling ``oma-platform/.env`` file (override with ``OMA_PLATFORM_ENV_FILE``).

Created agents/sessions/environments are kept after the run so they can be
inspected; set ``OMA_CLEANUP_RESOURCES=1`` to archive them instead.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

if sys.version_info < (3, 11):
    sys.exit("Python 3.11+ required")

from sdk import OMAClient, StreamConfig, stream_until_end_turn, wait_for_idle_status
from sdk.cookbook import event_payload, event_type, message_text, print_stream_event
from sdk.examples.agents import MODEL as DEFAULT_MODEL

OMA_BASE_URL = os.getenv("OMA_BASE_URL", "http://127.0.0.1:8787")
API_KEY = os.getenv("OMA_API_KEY", "dev-key")
os.environ.setdefault("OMA_API_KEY", API_KEY)
MODEL = os.getenv("OMA_MODEL", DEFAULT_MODEL["id"])
TENANT_ID_OVERRIDE = os.getenv("OMA_MEMORY_TENANT_ID", "").strip()


def _mask_key(key: str) -> str:
    return key[:8] + "..." + key[-4:] if len(key) > 16 else "***"


def _resolve_tenant_id() -> str:
    """Tenant for the internal memory check.

    Explicit OMA_MEMORY_TENANT_ID wins; otherwise ask GET /v1/me, which
    returns the tenant the API key authenticates as.
    """
    if TENANT_ID_OVERRIDE:
        return TENANT_ID_OVERRIDE
    resp = httpx.get(
        f"{OMA_BASE_URL}/v1/me",
        headers={"x-api-key": API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return (resp.json().get("tenant") or {}).get("id") or "default"

AGENT_NAME = "builtin-memory-test-agent"
ENV_NAME = "builtin-memory-test-env"
SESSION_SAVE_TITLE = "Builtin memory: save preference"
SESSION_RECALL_TITLE = "Builtin memory: recall preference"

SECRET_FACT = "乌龙茶"

AGENT_TOOLS = [
    {
        "type": "agent_toolset_20260401",
        "default_config": {
            "enabled": True,
            "permission_policy": {"type": "always_allow"},
        },
        "configs": [
            {"name": "read"},
            {"name": "write"},
        ],
    }
]

AGENT_SYSTEM = (
    "You are a helpful assistant with persistent long-term memory. "
    "You have a `memory` tool. Whenever the user tells you a fact or "
    "preference to remember, immediately call the memory tool with "
    'action="add" (target="user" for user preferences, target="memory" '
    "for project facts) and put the exact information into content. "
    "When the user later asks about something remembered earlier, answer "
    "directly from the memory snapshot provided to you."
)

SAVE_USER_MESSAGE = (
    "请记住：我喜欢喝乌龙茶。请立即调用 memory 工具"
    '（action="add"，target="user"）把这条偏好保存到记忆中，保存后用一句话确认。'
)

RECALL_USER_MESSAGE = "问题：我喜欢喝什么茶？请直接回答。"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def _load_internal_secret() -> str:
    secret = os.getenv("OMA_INTERNAL_SECRET", "").strip()
    if secret:
        return secret
    env_file = Path(
        os.getenv(
            "OMA_PLATFORM_ENV_FILE",
            str(Path(__file__).resolve().parents[3] / "oma-platform" / ".env"),
        )
    )
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OMA_INTERNAL_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(
        "OMA_INTERNAL_SECRET not set and oma-platform/.env not found; "
        "set OMA_INTERNAL_SECRET or OMA_PLATFORM_ENV_FILE"
    )


def _fetch_builtin_memory(agent_id: str, secret: str, tenant_id: str) -> dict[str, Any]:
    resp = httpx.get(
        f"{OMA_BASE_URL}/v1/internal/agent_memory",
        params={"tenant_id": tenant_id, "agent_id": agent_id},
        headers={"x-internal-secret": secret},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _stream_config() -> StreamConfig:
    return StreamConfig(
        timeout_sec=float(os.getenv("OMA_MEMORY_TEST_TIMEOUT_SEC", "600")),
        stream_read_timeout=float(os.getenv("OMA_STREAM_READ_TIMEOUT_SEC", "300")),
        idle_poll_max_wait=float(os.getenv("OMA_IDLE_POLL_MAX_WAIT_SEC", "60")),
    )


def _make_message_collector(texts: list[str]):
    def handler(ev: dict[str, Any]) -> None:
        print_stream_event(ev, preview_length=300)
        if event_type(ev) == "agent.message":
            text = message_text(event_payload(ev))
            if text:
                texts.append(text)

    return handler


async def _run_turn(
    client: OMAClient,
    session_id: str,
    user_message: str,
    cfg: StreamConfig,
) -> str:
    """Send one user message, stream to end_turn, return assistant text."""
    texts: list[str] = []
    await stream_until_end_turn(
        client,
        session_id,
        send_events=[
            {
                "type": "user.message",
                "content": [{"type": "text", "text": user_message}],
            },
        ],
        config=cfg,
        on_event=_make_message_collector(texts),
    )
    await wait_for_idle_status(client, session_id, max_wait=cfg.idle_poll_max_wait)
    # Streamed agent.message chunks can split mid-word (e.g. 乌龙 | 茶);
    # join without separators so substring checks are not broken.
    return "".join(texts)


async def run_builtin_memory_test(
    client: OMAClient,
    *,
    model: str,
    internal_secret: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Run the two-session built-in memory test."""
    agent = client.agents.create(
        name=AGENT_NAME,
        model={"id": model},
        system=AGENT_SYSTEM,
        tools=AGENT_TOOLS,
    )
    env = client.environments.create(
        name=ENV_NAME,
        config={"type": "local"},  # type: ignore[arg-type]
    )
    cfg = _stream_config()
    session1 = session2 = None
    try:
        # -- Session 1: save -------------------------------------------------
        session1 = client.sessions.create(
            environment_id=env.id,
            agent={"type": "agent", "id": agent.id, "version": agent.version},
            title=SESSION_SAVE_TITLE,
        )
        print(f"\n--- session 1 (save): {session1.id}")
        await _run_turn(client, session1.id, SAVE_USER_MESSAGE, cfg)

        # -- Platform persistence (agentmem-<agent_id>) ----------------------
        contents: dict[str, str] = {}
        store_id = ""
        for attempt in range(5):
            data = _fetch_builtin_memory(agent.id, internal_secret, tenant_id)
            contents = data.get("contents") or {}
            store_id = str(data.get("store_id") or "")
            if any(SECRET_FACT in body for body in contents.values()):
                break
            await asyncio.sleep(2)
        check(
            "store id is agentmem-<agent_id>",
            store_id == f"agentmem-{agent.id}",
            store_id,
        )
        persisted = {p: b for p, b in contents.items() if SECRET_FACT in b}
        check(
            "preference persisted to builtin memory",
            bool(persisted),
            f"files={sorted(contents)} hit={sorted(persisted)}",
        )

        # -- Session 2: recall (fresh session, snapshot injection) -----------
        session2 = client.sessions.create(
            environment_id=env.id,
            agent={"type": "agent", "id": agent.id, "version": agent.version},
            title=SESSION_RECALL_TITLE,
        )
        print(f"\n--- session 2 (recall): {session2.id}")
        recall_reply = await _run_turn(client, session2.id, RECALL_USER_MESSAGE, cfg)
        # Whitespace-tolerant match: streaming may insert line breaks anywhere.
        normalized_reply = "".join(recall_reply.split())
        check(
            "cross-session recall contains the fact",
            SECRET_FACT in normalized_reply,
            recall_reply[:120],
        )

        return {
            "agent_id": agent.id,
            "store_id": store_id,
            "session_save_id": session1.id,
            "session_recall_id": session2.id,
            "persisted_files": sorted(persisted),
            "recall_reply": recall_reply,
        }
    finally:
        if os.getenv("OMA_CLEANUP_RESOURCES") == "1":
            for sess in (session1, session2):
                if sess is not None:
                    client.sessions.archive(sess.id)
            client.agents.archive(agent.id)
            client.environments.archive(env.id)
        else:
            print(
                f"\n[KEEP] agent {agent.id} env {env.id} sessions "
                f"{getattr(session1, 'id', None)}/{getattr(session2, 'id', None)} "
                "— 已保留，未归档"
            )


async def main() -> None:
    internal_secret = _load_internal_secret()
    tenant_id = _resolve_tenant_id()
    print(
        f"config: base_url={OMA_BASE_URL} api_key={_mask_key(API_KEY)} "
        f"tenant={tenant_id} model={MODEL}"
    )
    started = time.time()
    async with OMAClient(
        base_url=OMA_BASE_URL, api_key=API_KEY, tenant_id=tenant_id
    ) as client:
        result = await run_builtin_memory_test(
            client,
            model=MODEL,
            internal_secret=internal_secret,
            tenant_id=tenant_id,
        )
    print("\n--- summary ---")
    print("agent:", result["agent_id"])
    print("store:", result["store_id"])
    print("persisted_files:", result["persisted_files"])
    print("recall_reply:", result["recall_reply"][:200])
    failed = [r for r in RESULTS if not r[1]]
    print(
        f"\n内置记忆 E2E：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过，"
        f"耗时 {time.time() - started:.1f}s"
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
