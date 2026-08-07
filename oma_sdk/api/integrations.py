from __future__ import annotations

from typing import Any

import httpx

from .._http import json_or_empty

PROVIDERS = ("github", "linear", "slack")


class IntegrationsResource:
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
                "sync IntegrationsResource methods require a sync httpx.Client"
            )
        return self._sync

    def list_installations(self, provider: str, **params: Any) -> dict:
        r = self._require_sync().get(
            f"/v1/integrations/{provider}/installations", params=params
        )
        return json_or_empty(r)

    def list_publications(self, provider: str, **params: Any) -> dict:
        r = self._require_sync().get(
            f"/v1/integrations/{provider}/publications", params=params
        )
        return json_or_empty(r)

    async def list_installations_async(self, provider: str, **params: Any) -> dict:
        r = await self._http.get(
            f"/v1/integrations/{provider}/installations", params=params
        )
        return json_or_empty(r)

    async def list_publications_async(self, provider: str, **params: Any) -> dict:
        r = await self._http.get(
            f"/v1/integrations/{provider}/publications", params=params
        )
        return json_or_empty(r)
