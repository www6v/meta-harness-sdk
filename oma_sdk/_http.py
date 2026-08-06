"""Shared httpx helpers for OMA resource classes."""

from __future__ import annotations

from typing import Any

import httpx

from ._exceptions import raise_for_status


def request_id_from(response: httpx.Response) -> str | None:
    return (
        response.headers.get("request-id")
        or response.headers.get("x-request-id")
        or response.headers.get("X-Request-Id")
    )


def json_or_empty(response: httpx.Response) -> dict[str, Any]:
    raise_for_status(response)
    if not response.content:
        return {}
    data = response.json()
    return data if isinstance(data, dict) else {"data": data}
