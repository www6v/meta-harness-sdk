"""Unit tests for OMA session-event flattening (no live server)."""

from __future__ import annotations

from types import SimpleNamespace

from oma_sdk.event_flatten import FlatteningEvents, flatten_session_event


def test_flatten_promotes_nested_content() -> None:
    ev = SimpleNamespace(
        type="agent.message",
        content=None,
        id=None,
        data={
            "type": "agent.message",
            "id": "evt-1",
            "content": [{"type": "text", "text": "hello"}],
        },
    )
    flat = flatten_session_event(ev)
    assert flat.type == "agent.message"
    assert flat.id == "evt-1"
    assert flat.content[0].text == "hello"
    assert not hasattr(flat, "data") or getattr(flat, "data", None) is None


def test_flatten_promotes_stop_reason() -> None:
    ev = SimpleNamespace(
        type="session.status_idle",
        stop_reason=None,
        data={
            "type": "session.status_idle",
            "id": "evt-idle",
            "stop_reason": {"type": "end_turn"},
        },
    )
    flat = flatten_session_event(ev)
    assert flat.stop_reason.type == "end_turn"


def test_flatten_promotes_custom_tool_fields() -> None:
    ev = SimpleNamespace(
        type="agent.custom_tool_use",
        name=None,
        input=None,
        id=None,
        data={
            "type": "agent.custom_tool_use",
            "id": "call-1",
            "name": "get_metrics",
            "input": {"service": "checkout", "metric": "p99"},
        },
    )
    flat = flatten_session_event(ev)
    assert flat.name == "get_metrics"
    assert flat.input["service"] == "checkout"
    assert flat.id == "call-1"


def test_flatten_leaves_already_flat_event() -> None:
    ev = SimpleNamespace(
        type="agent.message",
        content=[SimpleNamespace(type="text", text="hi")],
        data=None,
    )
    assert flatten_session_event(ev) is ev


def test_flattening_events_list_rewrites_page_data() -> None:
    raw = SimpleNamespace(
        type="agent.message",
        content=None,
        data={"type": "agent.message", "content": [{"type": "text", "text": "x"}]},
    )
    page = SimpleNamespace(data=[raw], has_more=False)

    class Inner:
        def list(self, *args, **kwargs):
            return page

        def send(self, *args, **kwargs):
            return {"status": "queued"}

    wrapped = FlatteningEvents(
        Inner(),
        base_url="http://127.0.0.1:8787",
        api_key="dev-key",
    )
    out = wrapped.list("sess-1")
    assert out.data[0].content[0].text == "x"


def test_flatten_already_flat_sse_payload() -> None:
    flat = flatten_session_event(
        {
            "type": "agent.message",
            "id": "evt-1",
            "content": [{"type": "text", "text": "pong"}],
        }
    )
    assert flat.type == "agent.message"
    assert flat.content[0].text == "pong"


def test_iter_sse_data_lines_reads_type_from_json() -> None:
    from oma_sdk.event_flatten import iter_sse_data_lines

    class FakeResponse:
        def iter_lines(self):
            yield "id: 1"
            yield 'data: {"type": "agent.message", "content": [{"type": "text", "text": "hi"}]}'
            yield ""

    rows = list(iter_sse_data_lines(FakeResponse()))  # type: ignore[arg-type]
    assert rows[0]["type"] == "agent.message"
    assert rows[0]["seq"] == 1
