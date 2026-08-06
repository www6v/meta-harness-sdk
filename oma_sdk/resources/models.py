from __future__ import annotations

from typing import Any

import httpx

from .._http import json_or_empty


class ModelsResource:
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
                "sync ModelsResource methods require a sync httpx.Client"
            )
        return self._sync

    def list(self, **params: Any) -> dict:
        r = self._require_sync().get("/v1/models/list", params=params)
        return json_or_empty(r)

    async def list_async(self, **params: Any) -> dict:
        r = await self._http.get("/v1/models/list", params=params)
        return json_or_empty(r)
