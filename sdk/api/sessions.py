"""
OMA-native session events resource.

Wraps the server's three events endpoints:

    POST /v1/sessions/{id}/events         -> send()
    GET  /v1/sessions/{id}/events         -> list()
    GET  /v1/sessions/{id}/events/stream  -> stream()  (SSE)

These are the raw server endpoints — distinct from the Anthropic SDK's
``client.beta.sessions.events`` wrapper, which speaks the managed-agents
protocol. Use this resource when you want direct access to the event log
(e.g. for replay, tailing, or feeding events from a non-Anthropic client).

Async methods (``send`` / ``list`` / ``stream``) are the primary surface used
by cookbook helpers. Sync counterparts use the ``*_sync`` suffix.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

import httpx

from .._exceptions import raise_for_status
from .._http import json_or_empty


class SessionEventsResource:
    """Send, list, and stream events on a session."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        sync: httpx.Client | None = None,
    ) -> None:
        self._http = http
        self._sync = sync

    def _require_sync(self) -> httpx.Client:
        if self._sync is None:
            raise RuntimeError(
                "sync SessionEventsResource methods require a sync httpx.Client"
            )
        return self._sync

    # -- sync ---------------------------------------------------------------

    def send_sync(
        self,
        session_id: str,
        events: list[dict[str, Any]],
    ) -> dict:
        r = self._require_sync().post(
            f"/v1/sessions/{session_id}/events",
            json={"events": events},
        )
        return json_or_empty(r)

    def list_sync(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        order: str | None = None,
        after_seq: int | None = None,
        next_page: str | None = None,
    ) -> dict:
        params = _list_params(
            limit=limit,
            order=order,
            after_seq=after_seq,
            next_page=next_page,
        )
        r = self._require_sync().get(
            f"/v1/sessions/{session_id}/events",
            params=params,
        )
        return json_or_empty(r)

    def stream_sync(
        self,
        session_id: str,
        *,
        replay: bool = False,
        timeout: float | None = None,
    ) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {}
        if replay:
            params["replay"] = "1"
        stream_kwargs: dict[str, Any] = {"params": params}
        if timeout is not None:
            stream_kwargs["timeout"] = timeout
        with self._require_sync().stream(
            "GET",
            f"/v1/sessions/{session_id}/events/stream",
            **stream_kwargs,
        ) as resp:
            raise_for_status(resp)
            yield from _iter_sse_events_sync(resp)

    # -- async (primary) ----------------------------------------------------

    async def send(
        self,
        session_id: str,
        events: list[dict[str, Any]],
    ) -> dict:
        """Append one or more events to a session.

        Returns ``{"status": "queued"}`` on success (HTTP 202).
        """
        r = await self._http.post(
            f"/v1/sessions/{session_id}/events",
            json={"events": events},
        )
        return json_or_empty(r)

    async def list(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        order: str | None = None,
        after_seq: int | None = None,
        next_page: str | None = None,
    ) -> dict:
        params = _list_params(
            limit=limit,
            order=order,
            after_seq=after_seq,
            next_page=next_page,
        )
        r = await self._http.get(
            f"/v1/sessions/{session_id}/events",
            params=params,
        )
        return json_or_empty(r)

    async def stream(
        self,
        session_id: str,
        *,
        replay: bool = False,
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Tail a session's event log as a server-sent event stream."""
        params: dict[str, Any] = {}
        if replay:
            params["replay"] = "1"

        stream_kwargs: dict[str, Any] = {"params": params}
        if timeout is not None:
            stream_kwargs["timeout"] = timeout

        async with self._http.stream(
            "GET",
            f"/v1/sessions/{session_id}/events/stream",
            **stream_kwargs,
        ) as resp:
            raise_for_status(resp)
            async for event in _iter_sse_events(resp):
                yield event


def _list_params(
    *,
    limit: int | None,
    order: str | None,
    after_seq: int | None,
    next_page: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if order is not None:
        params["order"] = order
    if after_seq is not None:
        params["after_seq"] = after_seq
    if next_page is not None:
        params["next_page"] = next_page
    return params


async def _iter_sse_events(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    current_id: str | None = None
    current_data: str | None = None

    async for raw in resp.aiter_lines():
        line = raw.rstrip("\r")
        if not line:
            if current_data is not None:
                event = _parse_sse_event(current_id, current_data)
                if event is not None:
                    yield event
            current_id = None
            current_data = None
            continue

        if line.startswith(":"):
            continue

        if line.startswith("id:"):
            current_id = line[3:].strip()
        elif line.startswith("data:"):
            chunk = line[5:]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            current_data = (
                chunk if current_data is None else f"{current_data}\n{chunk}"
            )


def _iter_sse_events_sync(resp: httpx.Response) -> Iterator[dict[str, Any]]:
    current_id: str | None = None
    current_data: str | None = None

    for raw in resp.iter_lines():
        line = raw.rstrip("\r")
        if not line:
            if current_data is not None:
                event = _parse_sse_event(current_id, current_data)
                if event is not None:
                    yield event
            current_id = None
            current_data = None
            continue

        if line.startswith(":"):
            continue

        if line.startswith("id:"):
            current_id = line[3:].strip()
        elif line.startswith("data:"):
            chunk = line[5:]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            current_data = (
                chunk if current_data is None else f"{current_data}\n{chunk}"
            )


def _parse_sse_event(
    event_id: str | None,
    data: str,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        payload = {"_raw": data}

    if not isinstance(payload, dict):
        payload = {"_raw": payload}

    if event_id is not None:
        try:
            payload.setdefault("seq", int(event_id))
        except ValueError:
            payload.setdefault("seq", event_id)
    return payload
