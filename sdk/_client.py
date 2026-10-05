"""OMA sync/async clients aligned with Anthropic / AsyncAnthropic DX."""

from __future__ import annotations

import logging
import os
from typing import Any

import anthropic
import httpx

from ._async_facade import (
    AsyncApiKeysFacade,
    AsyncCostReportFacade,
    AsyncDreamsFacade,
    AsyncEvalsFacade,
    AsyncFilesFacade,
    AsyncIntegrationsFacade,
    AsyncMeFacade,
    AsyncModelCardsFacade,
    AsyncModelsFacade,
    AsyncRuntimesFacade,
    AsyncSkillsFacade,
)
from .event_flatten import install_event_flattening
from .api.api_keys import ApiKeysResource
from .api.cost_report import CostReportResource
from .api.dreams import DreamsResource
from .api.evals import EvalsResource
from .api.files import FilesResource
from .api.integrations import IntegrationsResource
from .api.me import MeResource
from .api.model_cards import ModelCardsResource
from .api.models import ModelsResource
from .api.runtimes import RuntimesResource
from .api.sessions import SessionEventsResource
from .api.skills import SkillsResource

logger = logging.getLogger("sdk")

DEFAULT_BASE_URL = "http://localhost:8787"
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 2


def _configure_logging() -> None:
    level_name = (os.environ.get("OMA_LOG") or "").strip().lower()
    if not level_name:
        return
    level = logging.DEBUG if level_name == "debug" else logging.INFO
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[sdk] %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(level)


def _resolve_api_key(api_key: str | None) -> str:
    key = api_key if api_key is not None else os.environ.get("OMA_API_KEY")
    if not key:
        raise anthropic.AnthropicError(
            "The api_key client option must be set either by passing api_key "
            "to the client or by setting the OMA_API_KEY environment variable"
        )
    return key


def _resolve_base_url(base_url: str | None) -> str:
    return base_url or os.environ.get("OMA_PLATFORM_URL", DEFAULT_BASE_URL)


def _merge_headers(
    *,
    tenant_id: str | None,
    default_headers: dict[str, str] | None,
) -> dict[str, str]:
    headers: dict[str, str] = dict(default_headers or {})
    if tenant_id:
        headers.setdefault("x-active-tenant", tenant_id)
    return headers


class _ClientOptions:
    """Immutable-ish option bag shared by sync/async clients."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float | httpx.Timeout,
        max_retries: int,
        default_headers: dict[str, str],
        tenant_id: str | None,
        http_client: Any | None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = default_headers
        self.tenant_id = tenant_id
        self.http_client = http_client


def _build_options(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    tenant_id: str | None = None,
    timeout: float | httpx.Timeout | None = None,
    max_retries: int | None = None,
    default_headers: dict[str, str] | None = None,
    http_client: Any | None = None,
) -> _ClientOptions:
    _configure_logging()
    resolved_key = _resolve_api_key(api_key)
    resolved_url = _resolve_base_url(base_url)
    headers = _merge_headers(
        tenant_id=tenant_id,
        default_headers=default_headers,
    )
    return _ClientOptions(
        api_key=resolved_key,
        base_url=resolved_url,
        timeout=DEFAULT_TIMEOUT if timeout is None else timeout,
        max_retries=DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
        default_headers=headers,
        tenant_id=tenant_id,
        http_client=http_client,
    )


class OMAClient:
    """Synchronous OMA platform client (Anthropic SDK + httpx)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        default_headers: dict[str, str] | None = None,
        http_client: httpx.Client | None = None,
        _opts: _ClientOptions | None = None,
    ) -> None:
        opts = _opts or _build_options(
            base_url=base_url,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self._opts = opts
        self._base_url = opts.base_url
        self._tenant_id = opts.tenant_id
        self._owns_http = http_client is None and opts.http_client is None

        anthropic_headers = dict(opts.default_headers)
        http_headers = {"x-api-key": opts.api_key, **opts.default_headers}

        self._anthropic = anthropic.Anthropic(
            api_key=opts.api_key,
            base_url=opts.base_url,
            timeout=opts.timeout,
            max_retries=opts.max_retries,
            default_headers=anthropic_headers,
            http_client=opts.http_client if isinstance(
                opts.http_client, httpx.Client
            ) else None,
        )
        install_event_flattening(
            self._anthropic,
            base_url=opts.base_url,
            api_key=opts.api_key,
            tenant_id=opts.tenant_id,
        )

        if isinstance(opts.http_client, httpx.Client):
            self._http_sync = opts.http_client
        else:
            self._http_sync = httpx.Client(
                base_url=opts.base_url,
                headers=http_headers,
                timeout=opts.timeout,
            )
        # Keep AsyncClient for cookbook / *_async compatibility on sync client.
        self._http = httpx.AsyncClient(
            base_url=opts.base_url,
            headers=http_headers,
            timeout=opts.timeout,
        )

        self._bind_resources(sync=True)

    def _bind_resources(self, *, sync: bool) -> None:
        self.dreams = DreamsResource(self._http, sync=self._http_sync)
        self.evals = EvalsResource(self._http, sync=self._http_sync)
        self.runtimes = RuntimesResource(self._http, sync=self._http_sync)
        self.integrations = IntegrationsResource(
            self._http, sync=self._http_sync
        )
        self.model_cards = ModelCardsResource(self._http, sync=self._http_sync)
        self.cost_report = CostReportResource(self._http, sync=self._http_sync)
        self.me = MeResource(self._http, sync=self._http_sync)
        self.api_keys = ApiKeysResource(self._http, sync=self._http_sync)
        self.files = FilesResource(self._http, sync=self._http_sync)
        self.skills = SkillsResource(self._http, self._http_sync)
        self.models = ModelsResource(self._http, sync=self._http_sync)
        self.events = SessionEventsResource(self._http, sync=self._http_sync)
        _ = sync  # sync client always binds hybrid resources

    @property
    def agents(self):
        return self._anthropic.beta.agents

    @property
    def sessions(self):
        return self._anthropic.beta.sessions

    @property
    def environments(self):
        return self._anthropic.beta.environments

    @property
    def memory_stores(self):
        return self._anthropic.beta.memory_stores

    @property
    def vaults(self):
        return self._anthropic.beta.vaults

    def with_options(self, **kwargs: Any) -> "OMAClient":
        """Return a new client with selected options overridden."""
        opts = self._opts
        merged_headers = dict(opts.default_headers)
        if "default_headers" in kwargs and kwargs["default_headers"]:
            merged_headers.update(kwargs["default_headers"])
        tenant = kwargs.get("tenant_id", opts.tenant_id)
        if tenant:
            merged_headers["x-active-tenant"] = tenant
        new_opts = _ClientOptions(
            api_key=kwargs.get("api_key", opts.api_key),
            base_url=kwargs.get("base_url", opts.base_url),
            timeout=kwargs.get("timeout", opts.timeout),
            max_retries=kwargs.get("max_retries", opts.max_retries),
            default_headers=merged_headers,
            tenant_id=tenant,
            http_client=kwargs.get("http_client", None),
        )
        return OMAClient(_opts=new_opts)

    def close(self) -> None:
        """Close sync + async httpx clients (safe from sync CLIs)."""
        if self._owns_http:
            try:
                self._http_sync.close()
            except Exception:
                pass
        try:
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._http.aclose())
        except Exception:
            pass

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._owns_http:
            try:
                self._http_sync.close()
            except Exception:
                pass

    async def __aenter__(self) -> "OMAClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    def __enter__(self) -> "OMAClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class AsyncOMAClient:
    """Asynchronous OMA platform client (AsyncAnthropic + httpx.AsyncClient)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        default_headers: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        _opts: _ClientOptions | None = None,
    ) -> None:
        opts = _opts or _build_options(
            base_url=base_url,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self._opts = opts
        self._base_url = opts.base_url
        self._tenant_id = opts.tenant_id
        self._owns_http = http_client is None and opts.http_client is None

        anthropic_headers = dict(opts.default_headers)
        http_headers = {"x-api-key": opts.api_key, **opts.default_headers}

        self._anthropic = anthropic.AsyncAnthropic(
            api_key=opts.api_key,
            base_url=opts.base_url,
            timeout=opts.timeout,
            max_retries=opts.max_retries,
            default_headers=anthropic_headers,
            http_client=opts.http_client if isinstance(
                opts.http_client, httpx.AsyncClient
            ) else None,
        )
        # Event flattening patches sync SSE helpers; AsyncAnthropic still
        # benefits from list flattening. Stream uses async httpx resources.
        install_event_flattening(
            self._anthropic,
            base_url=opts.base_url,
            api_key=opts.api_key,
            tenant_id=opts.tenant_id,
        )

        if isinstance(opts.http_client, httpx.AsyncClient):
            self._http = opts.http_client
        else:
            self._http = httpx.AsyncClient(
                base_url=opts.base_url,
                headers=http_headers,
                timeout=opts.timeout,
            )
        # Optional sync peer for resources that still require sync helpers.
        self._http_sync = httpx.Client(
            base_url=opts.base_url,
            headers=http_headers,
            timeout=opts.timeout,
        )

        dreams = DreamsResource(self._http, sync=self._http_sync)
        evals = EvalsResource(self._http, sync=self._http_sync)
        runtimes = RuntimesResource(self._http, sync=self._http_sync)
        integrations = IntegrationsResource(self._http, sync=self._http_sync)
        model_cards = ModelCardsResource(self._http, sync=self._http_sync)
        cost_report = CostReportResource(self._http, sync=self._http_sync)
        me = MeResource(self._http, sync=self._http_sync)
        api_keys = ApiKeysResource(self._http, sync=self._http_sync)
        files = FilesResource(self._http, sync=self._http_sync)
        skills = SkillsResource(self._http, self._http_sync)
        models = ModelsResource(self._http, sync=self._http_sync)

        self.dreams = AsyncDreamsFacade(dreams)
        self.evals = AsyncEvalsFacade(evals)
        self.runtimes = AsyncRuntimesFacade(runtimes)
        self.integrations = AsyncIntegrationsFacade(integrations)
        self.model_cards = AsyncModelCardsFacade(model_cards)
        self.cost_report = AsyncCostReportFacade(cost_report)
        self.me = AsyncMeFacade(me)
        self.api_keys = AsyncApiKeysFacade(api_keys)
        self.files = AsyncFilesFacade(files)
        self.skills = AsyncSkillsFacade(skills)
        self.models = AsyncModelsFacade(models)
        self.events = SessionEventsResource(self._http, sync=self._http_sync)

    @property
    def agents(self):
        return self._anthropic.beta.agents

    @property
    def sessions(self):
        return self._anthropic.beta.sessions

    @property
    def environments(self):
        return self._anthropic.beta.environments

    @property
    def memory_stores(self):
        return self._anthropic.beta.memory_stores

    @property
    def vaults(self):
        return self._anthropic.beta.vaults

    def with_options(self, **kwargs: Any) -> "AsyncOMAClient":
        opts = self._opts
        merged_headers = dict(opts.default_headers)
        if "default_headers" in kwargs and kwargs["default_headers"]:
            merged_headers.update(kwargs["default_headers"])
        tenant = kwargs.get("tenant_id", opts.tenant_id)
        if tenant:
            merged_headers["x-active-tenant"] = tenant
        new_opts = _ClientOptions(
            api_key=kwargs.get("api_key", opts.api_key),
            base_url=kwargs.get("base_url", opts.base_url),
            timeout=kwargs.get("timeout", opts.timeout),
            max_retries=kwargs.get("max_retries", opts.max_retries),
            default_headers=merged_headers,
            tenant_id=tenant,
            http_client=kwargs.get("http_client", None),
        )
        return AsyncOMAClient(_opts=new_opts)

    async def aclose(self) -> None:
        await self._http.aclose()
        try:
            self._http_sync.close()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._http_sync.close()
        except Exception:
            pass
        try:
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._http.aclose())
        except Exception:
            pass

    async def __aenter__(self) -> "AsyncOMAClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    def __enter__(self) -> "AsyncOMAClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
