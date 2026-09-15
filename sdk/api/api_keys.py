from __future__ import annotations

from typing import Any

import httpx

from .._http import json_or_empty


class ApiKeysResource:
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
                "sync ApiKeysResource methods require a sync httpx.Client"
            )
        return self._sync

    def create(self, name: str, **kwargs: Any) -> dict:
        r = self._require_sync().post(
            "/v1/api_keys", json={"name": name, **kwargs}
        )
        return json_or_empty(r)

    def list(self, **params: Any) -> dict:
        r = self._require_sync().get("/v1/api_keys", params=params)
        return json_or_empty(r)

    def delete(self, key_id: str) -> dict:
        r = self._require_sync().delete(f"/v1/api_keys/{key_id}")
        return json_or_empty(r)

    async def create_async(self, name: str, **kwargs: Any) -> dict:
        r = await self._http.post(
            "/v1/api_keys", json={"name": name, **kwargs}
        )
        return json_or_empty(r)

    async def list_async(self, **params: Any) -> dict:
        r = await self._http.get("/v1/api_keys", params=params)
        return json_or_empty(r)

    async def delete_async(self, key_id: str) -> dict:
        r = await self._http.delete(f"/v1/api_keys/{key_id}")
        return json_or_empty(r)
