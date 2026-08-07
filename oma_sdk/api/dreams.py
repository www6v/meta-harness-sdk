from __future__ import annotations

from typing import Any

import httpx

from .._http import json_or_empty

_BETA = "managed-agents-2026-04-01,dreaming-2026-04-21"


class DreamsResource:
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
                "sync DreamsResource methods require a sync httpx.Client"
            )
        return self._sync

    def create(self, agent_id: str, **kwargs: Any) -> dict:
        r = self._require_sync().post(
            "/v1/dreams",
            json={"agent_id": agent_id, **kwargs},
            headers={"anthropic-beta": _BETA},
        )
        return json_or_empty(r)

    def list(self, agent_id: str | None = None, **params: Any) -> dict:
        query: dict = {**params}
        if agent_id:
            query["agent_id"] = agent_id
        r = self._require_sync().get(
            "/v1/dreams", params=query, headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    def retrieve(self, dream_id: str) -> dict:
        r = self._require_sync().get(
            f"/v1/dreams/{dream_id}", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    def cancel(self, dream_id: str) -> dict:
        r = self._require_sync().post(
            f"/v1/dreams/{dream_id}/cancel", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    def archive(self, dream_id: str) -> dict:
        r = self._require_sync().post(
            f"/v1/dreams/{dream_id}/archive", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    async def create_async(self, agent_id: str, **kwargs: Any) -> dict:
        r = await self._http.post(
            "/v1/dreams",
            json={"agent_id": agent_id, **kwargs},
            headers={"anthropic-beta": _BETA},
        )
        return json_or_empty(r)

    async def list_async(self, agent_id: str | None = None, **params: Any) -> dict:
        query: dict = {**params}
        if agent_id:
            query["agent_id"] = agent_id
        r = await self._http.get(
            "/v1/dreams", params=query, headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    async def retrieve_async(self, dream_id: str) -> dict:
        r = await self._http.get(
            f"/v1/dreams/{dream_id}", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    async def cancel_async(self, dream_id: str) -> dict:
        r = await self._http.post(
            f"/v1/dreams/{dream_id}/cancel", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)

    async def archive_async(self, dream_id: str) -> dict:
        r = await self._http.post(
            f"/v1/dreams/{dream_id}/archive", headers={"anthropic-beta": _BETA}
        )
        return json_or_empty(r)
