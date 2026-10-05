"""Unit tests for OMAClient / AsyncOMAClient DX (no live platform required)."""

from __future__ import annotations

import os

import httpx
import pytest
from anthropic import AnthropicError

from sdk import AsyncOMAClient, NotFoundError, OMAClient
from sdk._exceptions import make_status_error, raise_for_status


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMA_API_KEY", raising=False)
    with pytest.raises(AnthropicError, match="OMA_API_KEY"):
        OMAClient(base_url="http://127.0.0.1:8787")


def test_api_key_constructor_param(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMA_API_KEY", raising=False)
    client = OMAClient(base_url="http://127.0.0.1:8787", api_key="test-key")
    try:
        assert client._opts.api_key == "test-key"
        assert client._opts.max_retries == 2
        assert client._opts.timeout == 120.0
    finally:
        client.close()


def test_with_options_overrides_timeout() -> None:
    os.environ.setdefault("OMA_API_KEY", "dev-key")
    client = OMAClient(base_url="http://127.0.0.1:8787", api_key="dev-key")
    try:
        other = client.with_options(timeout=30.0, max_retries=0)
        assert other._opts.timeout == 30.0
        assert other._opts.max_retries == 0
        assert other._opts.api_key == "dev-key"
        other.close()
    finally:
        client.close()


def test_context_manager_closes() -> None:
    os.environ.setdefault("OMA_API_KEY", "dev-key")
    with OMAClient(base_url="http://127.0.0.1:8787", api_key="dev-key") as client:
        assert client.agents is not None


@pytest.mark.asyncio
async def test_async_client_context_manager() -> None:
    os.environ.setdefault("OMA_API_KEY", "dev-key")
    async with AsyncOMAClient(
        base_url="http://127.0.0.1:8787", api_key="dev-key"
    ) as client:
        assert client.agents is not None
        assert hasattr(client.files, "upload")
        assert hasattr(client.dreams, "create")


def test_make_status_error_maps_404() -> None:
    response = httpx.Response(404, json={"error": "missing"}, request=httpx.Request("GET", "http://x"))
    err = make_status_error(response)
    assert isinstance(err, NotFoundError)
    assert err.status_code == 404


def test_raise_for_status_ok() -> None:
    response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "http://x"))
    assert raise_for_status(response) is response


def test_oma_log_env_configures_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    import logging

    monkeypatch.setenv("OMA_LOG", "debug")
    monkeypatch.setenv("OMA_API_KEY", "dev-key")
    client = OMAClient(base_url="http://127.0.0.1:8787", api_key="dev-key")
    try:
        logger = logging.getLogger("sdk")
        assert logger.level == logging.DEBUG
    finally:
        client.close()
