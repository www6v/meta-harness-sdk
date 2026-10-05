"""
OMA Platform Python SDK.

Usage:
    import os
    os.environ["OMA_API_KEY"] = "your-key"

    from sdk import OMAClient, AsyncOMAClient
    client = OMAClient()                          # reads OMA_PLATFORM_URL, else http://localhost:8787
    client = OMAClient(base_url="http://...", api_key="...")

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

On ``OMAClient``, async variants use the ``*_async`` suffix.
On ``AsyncOMAClient``, use the same method names with ``await``.
"""

from __future__ import annotations

from ._client import AsyncOMAClient, OMAClient
from ._exceptions import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from .event_flatten import flatten_session_event
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
    "AsyncOMAClient",
    "OMAClient",
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "UnprocessableEntityError",
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
