"""Async facades so AsyncOMAClient uses unsuffixed method names."""

from __future__ import annotations

from typing import Any

from .resources.files import FilesResource
from .resources.skills import SkillsResource, SkillVersionsResource
from .resources.models_base import APIObject, SyncPage


class AsyncFilesFacade:
    """``await client.files.upload(...)`` — wraps ``FilesResource`` async methods."""

    def __init__(self, inner: FilesResource) -> None:
        self._inner = inner

    async def list(self, **kwargs: Any) -> SyncPage:
        return await self._inner.list_async(**kwargs)

    async def retrieve(self, file_id: str) -> APIObject:
        return await self._inner.retrieve_async(file_id)

    async def retrieve_metadata(self, file_id: str) -> APIObject:
        return await self._inner.retrieve_async(file_id)

    async def upload(self, **kwargs: Any) -> APIObject:
        return await self._inner.upload_async(**kwargs)

    async def download(self, file_id: str) -> bytes:
        return await self._inner.download_async(file_id)

    async def content(self, file_id: str) -> bytes:
        return await self._inner.content_async(file_id)

    async def delete(self, file_id: str) -> APIObject:
        return await self._inner.delete_async(file_id)

    # Compat aliases
    async def list_async(self, **kwargs: Any) -> SyncPage:
        return await self.list(**kwargs)

    async def retrieve_async(self, file_id: str) -> APIObject:
        return await self.retrieve(file_id)

    async def upload_async(self, **kwargs: Any) -> APIObject:
        return await self.upload(**kwargs)

    async def download_async(self, file_id: str) -> bytes:
        return await self.download(file_id)

    async def content_async(self, file_id: str) -> bytes:
        return await self.content(file_id)

    async def delete_async(self, file_id: str) -> APIObject:
        return await self.delete(file_id)


class AsyncSkillVersionsFacade:
    def __init__(self, inner: SkillVersionsResource) -> None:
        self._inner = inner

    async def create(self, skill_id: str, **kwargs: Any) -> APIObject:
        return await self._inner.create_async(skill_id, **kwargs)

    async def list(self, skill_id: str, **kwargs: Any) -> SyncPage:
        return await self._inner.list_async(skill_id, **kwargs)

    async def retrieve(self, version: str, *, skill_id: str) -> APIObject:
        return await self._inner.retrieve_async(version, skill_id=skill_id)

    async def delete(self, version: str, *, skill_id: str) -> APIObject:
        return await self._inner.delete_async(version, skill_id=skill_id)

    async def download(self, version: str, *, skill_id: str) -> bytes:
        return await self._inner.download_async(version, skill_id=skill_id)

    async def upload(self, skill_id: str, **kwargs: Any) -> APIObject:
        return await self._inner.upload_async(skill_id, **kwargs)

    async def create_async(self, skill_id: str, **kwargs: Any) -> APIObject:
        return await self.create(skill_id, **kwargs)

    async def list_async(self, skill_id: str, **kwargs: Any) -> SyncPage:
        return await self.list(skill_id, **kwargs)

    async def upload_async(self, skill_id: str, **kwargs: Any) -> APIObject:
        return await self.upload(skill_id, **kwargs)


class AsyncSkillsFacade:
    def __init__(self, inner: SkillsResource) -> None:
        self._inner = inner
        self.versions = AsyncSkillVersionsFacade(inner.versions)

    async def create(self, **kwargs: Any) -> APIObject:
        return await self._inner.create_async(**kwargs)

    async def list(self, **kwargs: Any) -> SyncPage:
        return await self._inner.list_async(**kwargs)

    async def retrieve(self, skill_id: str) -> APIObject:
        return await self._inner.retrieve_async(skill_id)

    async def delete(self, skill_id: str) -> APIObject:
        return await self._inner.delete_async(skill_id)

    async def upload(
        self,
        *,
        file: Any,
        display_title: str | None = None,
        filename: str = "skill.zip",
    ) -> APIObject:
        return await self._inner.upload_async(
            file=file, display_title=display_title, filename=filename
        )

    async def create_async(self, **kwargs: Any) -> APIObject:
        return await self.create(**kwargs)

    async def list_async(self, **kwargs: Any) -> SyncPage:
        return await self.list(**kwargs)

    async def retrieve_async(self, skill_id: str) -> APIObject:
        return await self.retrieve(skill_id)

    async def delete_async(self, skill_id: str) -> APIObject:
        return await self.delete(skill_id)

    async def upload_async(self, **kwargs: Any) -> APIObject:
        return await self.upload(**kwargs)


class AsyncDreamsFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def create(self, agent_id: str, **kwargs: Any) -> dict:
        return await self._inner.create_async(agent_id, **kwargs)

    async def list(self, agent_id: str | None = None, **params: Any) -> dict:
        return await self._inner.list_async(agent_id, **params)

    async def retrieve(self, dream_id: str) -> dict:
        return await self._inner.retrieve_async(dream_id)

    async def cancel(self, dream_id: str) -> dict:
        return await self._inner.cancel_async(dream_id)

    async def archive(self, dream_id: str) -> dict:
        return await self._inner.archive_async(dream_id)


class AsyncEvalsFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def create(self, **kwargs: Any) -> dict:
        return await self._inner.create_async(**kwargs)

    async def list(self, **params: Any) -> dict:
        return await self._inner.list_async(**params)

    async def retrieve(self, eval_id: str) -> dict:
        return await self._inner.retrieve_async(eval_id)


class AsyncRuntimesFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list(self, **params: Any) -> dict:
        return await self._inner.list_async(**params)

    async def retrieve(self, runtime_id: str) -> dict:
        return await self._inner.retrieve_async(runtime_id)


class AsyncIntegrationsFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list_installations(self, provider: str, **params: Any) -> dict:
        return await self._inner.list_installations_async(provider, **params)

    async def list_publications(self, provider: str, **params: Any) -> dict:
        return await self._inner.list_publications_async(provider, **params)


class AsyncModelCardsFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list(self, **params: Any) -> dict:
        return await self._inner.list_async(**params)

    async def retrieve(self, model_card_id: str) -> dict:
        return await self._inner.retrieve_async(model_card_id)


class AsyncModelsFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list(self, **params: Any) -> dict:
        return await self._inner.list_async(**params)


class AsyncMeFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get(self) -> dict:
        return await self._inner.get_async()


class AsyncApiKeysFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def create(self, name: str, **kwargs: Any) -> dict:
        return await self._inner.create_async(name, **kwargs)

    async def list(self, **params: Any) -> dict:
        return await self._inner.list_async(**params)

    async def delete(self, key_id: str) -> dict:
        return await self._inner.delete_async(key_id)


class AsyncCostReportFacade:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def get(self, **params: Any) -> dict:
        return await self._inner.get_async(**params)
