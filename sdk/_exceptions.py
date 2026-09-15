"""Map httpx responses to Anthropic-style typed API errors."""

from __future__ import annotations

import json
from typing import Any

import httpx
from anthropic import (
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

# Re-export for ``from sdk import NotFoundError`` convenience.
__all__ = [
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
    "make_status_error",
    "raise_for_status",
]


def make_status_error(response: httpx.Response) -> APIStatusError:
    """Build an Anthropic ``APIStatusError`` subclass from an httpx response."""
    try:
        err_text = response.text.strip()
    except Exception:
        err_text = ""
    body: Any = err_text
    try:
        body = json.loads(err_text) if err_text else None
        err_msg = f"Error code: {response.status_code} - {body}"
    except Exception:
        err_msg = err_text or f"Error code: {response.status_code}"

    code = response.status_code
    if code == 400:
        return BadRequestError(err_msg, response=response, body=body)
    if code == 401:
        return AuthenticationError(err_msg, response=response, body=body)
    if code == 403:
        return PermissionDeniedError(err_msg, response=response, body=body)
    if code == 404:
        return NotFoundError(err_msg, response=response, body=body)
    if code == 409:
        return ConflictError(err_msg, response=response, body=body)
    if code == 422:
        return UnprocessableEntityError(err_msg, response=response, body=body)
    if code == 429:
        return RateLimitError(err_msg, response=response, body=body)
    if code >= 500:
        return InternalServerError(err_msg, response=response, body=body)
    return APIStatusError(err_msg, response=response, body=body)


def raise_for_status(response: httpx.Response) -> httpx.Response:
    """Raise a typed Anthropic error if the response is not successful."""
    if response.is_success:
        return response
    raise make_status_error(response)
