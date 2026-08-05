"""
Flatten OMA session-event envelopes for Anthropic SDK consumers.

oma-platform persists and streams events as::

    {"seq": N, "type": "agent.message", "ts": "...", "data": {...fields...}}

The Anthropic managed-agents wire format (and ``agent_complete.py`` /
Streamlit ``provided.py``) expect the fields on the event itself::

    {"type": "agent.message", "content": [...], "id": "..."}

Without flattening, ``ev.content`` / ``ev.stop_reason`` / ``ev.name`` are
``None`` even though the payload is present under ``ev.data`` — which is why
a session can look healthy in the OMA Console while a Streamlit chat bubble
stays blank.

Streaming note
--------------
Anthropic's ``Stream.__stream__`` only yields frames whose SSE ``event:``
field is in a hard-coded whitelist. Older oma-platform builds emit only
``id:`` + ``data:`` lines, so the Anthropic iterator silently drops every
frame and hangs. ``FlatteningEvents.stream`` therefore uses a direct httpx
SSE reader that keys off JSON ``type`` (and still works when ``event:`` is
present).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Iterator

import httpx


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else None
    if hasattr(value, "__dict__"):
        raw = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        return raw or None
    return None


def _attrify(value: Any) -> Any:
    """Recursively turn dicts into attribute-accessible namespaces."""
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: _attrify(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return [_attrify(item) for item in value]
    return value


def flatten_session_event(ev: Any) -> Any:
    """Return an event whose payload fields are on the top level.

    Already-flat Anthropic events (no nested ``data`` payload, or top-level
    fields already populated) are returned unchanged.
    """
    envelope = _as_dict(ev) or {}
    nested = _as_dict(envelope.get("data"))
    if not nested:
        # Might still be a live SDK object with a dict ``data`` attr.
        nested = _as_dict(getattr(ev, "data", None))
    if not nested:
        # Live SSE payloads are already-flat JSON dicts — attrify them so
        # ``ev.type`` / ``ev.content`` work like Anthropic models.
        if isinstance(ev, dict):
            return _finalize_flat(dict(ev))
        return ev

    # Prefer already-populated top-level fields; fill gaps from ``data``.
    merged: dict[str, Any] = dict(envelope)
    for key, value in nested.items():
        if key == "type":
            continue
        if merged.get(key) is None:
            merged[key] = value

    # Keep envelope metadata.
    if envelope.get("type"):
        merged["type"] = envelope["type"]
    elif nested.get("type"):
        merged["type"] = nested["type"]

    # Drop the raw envelope so consumers don't double-read.
    merged.pop("data", None)
    return _finalize_flat(merged)


def _finalize_flat(merged: dict[str, Any]) -> Any:
    # Content blocks and stop_reason need attribute access (``b.text``,
    # ``stop_reason.type``). Keep ``input`` as a plain dict for json.dumps.
    content = merged.get("content")
    if isinstance(content, list):
        merged["content"] = [
            _attrify(block) if isinstance(block, dict) else block
            for block in content
        ]
    stop_reason = merged.get("stop_reason")
    if isinstance(stop_reason, dict):
        merged["stop_reason"] = _attrify(stop_reason)
    return SimpleNamespace(**merged)


def iter_sse_data_lines(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Parse an OMA ``text/event-stream`` body into JSON payloads."""
    current_id: str | None = None
    current_data: str | None = None
    current_event: str | None = None

    for raw in response.iter_lines():
        line = raw.rstrip("\r")
        if not line:
            if current_data is not None:
                try:
                    payload = json.loads(current_data)
                except json.JSONDecodeError:
                    payload = {"_raw": current_data}
                if isinstance(payload, dict):
                    if current_id is not None:
                        try:
                            payload.setdefault("seq", int(current_id))
                        except ValueError:
                            payload.setdefault("seq", current_id)
                    if current_event and not payload.get("type"):
                        payload["type"] = current_event
                    yield payload
            current_id = None
            current_data = None
            current_event = None
            continue

        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            current_id = line[3:].strip()
        elif line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            chunk = line[5:]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            current_data = (
                chunk if current_data is None else f"{current_data}\n{chunk}"
            )


class FlatteningEvents:
    """Wrap ``client.beta.sessions.events`` and flatten list/stream payloads."""

    def __init__(
        self,
        inner: Any,
        *,
        base_url: str,
        api_key: str,
        tenant_id: str | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> None:
        self._inner = inner
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id
        # Long agent turns (thinking + tools) easily exceed httpx's 5s default.
        self._timeout = timeout or httpx.Timeout(
            connect=30.0,
            read=300.0,
            write=30.0,
            pool=30.0,
        )

    def send(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.send(*args, **kwargs)

    def list(self, *args: Any, **kwargs: Any) -> Any:
        page = self._inner.list(*args, **kwargs)
        data = getattr(page, "data", None)
        if data is None:
            return page
        flat = [flatten_session_event(ev) for ev in data]
        if hasattr(page, "model_copy"):
            try:
                return page.model_copy(update={"data": flat})
            except Exception:
                pass
        # Duck-type a page object for workshop / cookbook callers.
        out = SimpleNamespace(**{
            key: getattr(page, key)
            for key in dir(page)
            if not key.startswith("_") and key != "data"
            and not callable(getattr(page, key, None))
        })
        out.data = flat
        return out

    def stream(
        self,
        session_id: str,
        *,
        replay: bool = False,
        **kwargs: Any,
    ) -> "_HttpxSSEStreamCM":
        """Stream session events via OMA's native SSE endpoint.

        ``replay=True`` replays persisted events before live tailing (same as
        Console ``?replay=1``). Extra kwargs are accepted for Anthropic SDK
        call-site compatibility and ignored.
        """
        del kwargs  # anthropic event_deltas / betas / timeout unused here
        return _HttpxSSEStreamCM(
            base_url=self._base_url,
            api_key=self._api_key,
            session_id=session_id,
            tenant_id=self._tenant_id,
            replay=replay,
            timeout=self._timeout,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _HttpxSSEStreamCM:
    """Context manager mirroring ``with client.beta.sessions.events.stream``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        session_id: str,
        tenant_id: str | None,
        replay: bool,
        timeout: float | httpx.Timeout,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._session_id = session_id
        self._tenant_id = tenant_id
        self._replay = replay
        self._timeout = timeout
        self._client: httpx.Client | None = None
        self._stream_cm: Any = None
        self._response: httpx.Response | None = None

    def __enter__(self) -> "_HttpxSSEStreamCM":
        headers = {"x-api-key": self._api_key, "accept": "text/event-stream"}
        if self._tenant_id:
            headers["x-active-tenant"] = self._tenant_id
        params = {"replay": "1"} if self._replay else None
        self._client = httpx.Client(timeout=self._timeout)
        self._stream_cm = self._client.stream(
            "GET",
            f"{self._base_url}/v1/sessions/{self._session_id}/events/stream",
            headers=headers,
            params=params,
        )
        self._response = self._stream_cm.__enter__()
        self._response.raise_for_status()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._stream_cm is not None:
            self._stream_cm.__exit__(*exc)
            self._stream_cm = None
            self._response = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def __iter__(self) -> Iterator[Any]:
        if self._response is None:
            return
        for payload in iter_sse_data_lines(self._response):
            yield flatten_session_event(payload)


def install_event_flattening(
    anthropic_client: Any,
    *,
    base_url: str,
    api_key: str,
    tenant_id: str | None = None,
) -> FlatteningEvents:
    """Patch ``client.beta.sessions.events`` in-place; return the wrapper."""
    sessions = anthropic_client.beta.sessions
    wrapper = FlatteningEvents(
        sessions.events,
        base_url=base_url,
        api_key=api_key,
        tenant_id=tenant_id,
    )
    sessions.events = wrapper
    return wrapper
