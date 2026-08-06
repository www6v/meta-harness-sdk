"""
OMA Platform Python SDK.

Usage:
    import os
    os.environ["OMA_API_KEY"] = "your-key"

    from oma_sdk import OMAClient
    client = OMAClient()                          # reads OMA_PLATFORM_URL, else http://localhost:8787
    client = OMAClient(base_url="http://...")     # custom server

Managed-agents resources (routed through anthropic SDK with custom base_url):
    client.agents, client.sessions, client.environments,
    client.memory_stores, client.vaults

OMA-platform resources (httpx — CMA-aligned sync API):
    client.skills, client.files, client.dreams, client.evals, client.runtimes,
    client.integrations, client.model_cards, client.cost_report,
    client.me, client.api_keys, client.models, client.events

Skills/files (aligned with Anthropic ``client.beta.skills`` / ``beta.files``)::

    client.skills.create(display_title=..., files=[(\"x.zip\", buf)])
    client.skills.list(limit=100)                 # iterable page
    client.skills.versions.create(skill_id, files=[...])
    client.files.upload(file=(name, f, \"text/csv\"))
    client.files.list(scope_id=session.id)
    client.files.download(file_id)

Async variants use the ``*_async`` suffix (``upload_async``, …).
"""

from __future__ import annotations

import os

import anthropic
import httpx

from .resources.api_keys import ApiKeysResource
from .resources.cost_report import CostReportResource
from .resources.dreams import DreamsResource
from .resources.evals import EvalsResource
from .resources.files import FilesResource
from .resources.integrations import IntegrationsResource
from .resources.me import MeResource
from .resources.model_cards import ModelCardsResource
from .resources.models import ModelsResource
from .resources.runtimes import RuntimesResource
from .resources.sessions import SessionEventsResource
from .resources.skills import SkillsResource
from .event_flatten import flatten_session_event, install_event_flattening

from .subagent import (
    build_multiagent,
    count_thread_created,
    events_of_type,
)
from .cookbook import (
    StreamConfig,
    custom_tool_event_id,
    event_payload,
    event_type,
    message_text,
    print_stream_event,
    stop_reason_event_ids,
    stop_reason_type,
    stream_hitl_until_end_turn,
    stream_until_end_turn,
    wait_for_idle_status,
)

__all__ = [
    "OMAClient",
    "StreamConfig",
    "build_multiagent",
    "count_thread_created",
    "custom_tool_event_id",
    "event_payload",
    "event_type",
    "events_of_type",
    "flatten_session_event",
    "message_text",
    "print_stream_event",
    "stop_reason_event_ids",
    "stop_reason_type",
    "stream_hitl_until_end_turn",
    "stream_until_end_turn",
    "wait_for_idle_status",
]


class OMAClient:
    def __init__(
        self,
        base_url: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        # Resolve base_url: explicit arg > OMA_PLATFORM_URL env var > localhost default.
        # Mirrors the convention used by the anthropic SDK (ANTHROPIC_BASE_URL).
        base_url = base_url or os.environ.get("OMA_PLATFORM_URL", "http://localhost:8787")
        api_key = os.environ["OMA_API_KEY"]
        # Build headers for tenant isolation
        anthropic_headers = {}
        http_headers = {"x-api-key": api_key}
        if tenant_id:
            anthropic_headers["x-active-tenant"] = tenant_id
            http_headers["x-active-tenant"] = tenant_id
        self._anthropic = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url,
            default_headers=anthropic_headers,
        )
        # oma-platform nests event fields under ``data``; flatten so
        # ``client.beta.sessions.events`` matches Anthropic managed-agents
        # (ev.content / ev.stop_reason / ev.name work for Streamlit UIs).
        # Also replaces ``.stream`` with an httpx SSE reader — Anthropic's
        # Stream drops frames that lack an SSE ``event:`` field.
        install_event_flattening(
            self._anthropic,
            base_url=base_url,
            api_key=api_key,
            tenant_id=tenant_id,
        )
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=http_headers,
            timeout=120.0,
        )
        self._http_sync = httpx.Client(
            base_url=base_url,
            headers=http_headers,
            timeout=120.0,
        )
        self._base_url = base_url
        self._tenant_id = tenant_id

        # OMA-platform resources (httpx)
        self.dreams = DreamsResource(self._http)
        self.evals = EvalsResource(self._http)
        self.runtimes = RuntimesResource(self._http)
        self.integrations = IntegrationsResource(self._http)
        self.model_cards = ModelCardsResource(self._http)
        self.cost_report = CostReportResource(self._http)
        self.me = MeResource(self._http)
        self.api_keys = ApiKeysResource(self._http)
        self.files = FilesResource(self._http, sync=self._http_sync)
        self.skills = SkillsResource(self._http, self._http_sync)
        self.models = ModelsResource(self._http)
        self.events = SessionEventsResource(self._http)

    # Managed-agents resources — routed through the anthropic SDK
    @property
    def agents(self):
        return self._anthropic.beta.agents

    @property
    def sessions(self):
        return self._anthropic.beta.sessions

    @property
    def environments(self):
        return self._anthropic.beta.environments

    @property
    def memory_stores(self):
        return self._anthropic.beta.memory_stores

    @property
    def vaults(self):
        return self._anthropic.beta.vaults

    def close(self) -> None:
        """Close sync + async httpx clients (safe from sync CLIs)."""
        try:
            self._http_sync.close()
        except Exception:
            pass
        try:
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._http.aclose())
        except Exception:
            pass

    async def aclose(self) -> None:
        await self._http.aclose()
        try:
            self._http_sync.close()
        except Exception:
            pass

    async def __aenter__(self) -> "OMAClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    def __enter__(self) -> "OMAClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
