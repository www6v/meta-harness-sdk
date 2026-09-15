from __future__ import annotations

import httpx

from .._http import json_or_empty


class MeResource:
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
                "sync MeResource methods require a sync httpx.Client"
            )
        return self._sync

    def get(self) -> dict:
        r = self._require_sync().get("/v1/me")
        return json_or_empty(r)

    async def get_async(self) -> dict:
        r = await self._http.get("/v1/me")
        return json_or_empty(r)
