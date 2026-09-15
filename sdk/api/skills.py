"""Skills resource — CMA-aligned sync API over OMA ``/v1/skills``.

Matches Anthropic Managed Agents SDK shapes::

    client.skills.create(display_title=..., files=[(\"x.zip\", buf)])
    client.skills.list(limit=100)
    client.skills.retrieve(skill_id)
    client.skills.delete(skill_id)
    client.skills.versions.create(skill_id, files=[...])
    client.skills.versions.list(skill_id)

Zip tuples are posted to OMA ``/v1/skills/upload`` (and ``.../versions/upload``)
because Anthropic SDK multipart is rejected by oma-platform (``invalid json``).

Async variants use the ``*_async`` suffix for cookbook code that prefers await.
"""

from __future__ import annotations

import io
from typing import IO, Any

import httpx

from .._exceptions import raise_for_status
from .models_base import APIObject, SyncPage, wrap_page_response, wrap_response

FileTuple = tuple[str, bytes | str | IO[bytes]] | tuple[str, bytes | str | IO[bytes], str]


def _read_bytes(content: bytes | str | IO[bytes]) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    data = content.read()
    if isinstance(data, str):
        return data.encode("utf-8")
    return data


def _is_zip_tuple(item: Any) -> bool:
    if not isinstance(item, tuple) or len(item) < 2:
        return False
    return str(item[0]).endswith(".zip")


def _normalize_json_files(
    files: list[dict[str, str]] | list[FileTuple],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in files:
        if isinstance(item, dict):
            out.append({
                "filename": str(item["filename"]),
                "content": str(item["content"]),
            })
            continue
        if isinstance(item, tuple) and len(item) >= 2:
            raw = _read_bytes(item[1])
            out.append({
                "filename": str(item[0]),
                "content": raw.decode("utf-8"),
            })
            continue
        raise TypeError(
            "files items must be dict{filename,content} or "
            "(filename, content[, media_type])"
        )
    return out


def _zip_parts(
    file: FileTuple | bytes | IO[bytes],
    default_name: str,
) -> tuple[str, bytes]:
    if isinstance(file, tuple):
        return str(file[0]), _read_bytes(file[1])
    return default_name, _read_bytes(file)


class SkillVersionsResource:
    """``client.skills.versions`` — CMA-aligned sync (+ ``*_async``)."""

    def __init__(self, http: httpx.AsyncClient, sync: httpx.Client) -> None:
        self._http = http
        self._sync = sync

    # -- CMA sync -----------------------------------------------------------

    def create(
        self,
        skill_id: str,
        *,
        files: list[dict[str, str]] | list[FileTuple] | None = None,
        display_title: str | None = None,
        description: str | None = None,
    ) -> APIObject:
        """Create a version. Zip ``files=[(name.zip, bytes)]`` → multipart upload."""
        if files and len(files) == 1 and _is_zip_tuple(files[0]):
            return self.upload(
                skill_id,
                file=files[0],  # type: ignore[arg-type]
                display_title=display_title,
            )
        body: dict[str, Any] = {"files": _normalize_json_files(files or [])}
        if display_title is not None:
            body["display_title"] = display_title
        if description is not None:
            body["description"] = description
        r = self._sync.post(f"/v1/skills/{skill_id}/versions", json=body)
        return wrap_response(r)

    def list(self, skill_id: str, *, limit: int | None = None) -> SyncPage:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        r = self._sync.get(f"/v1/skills/{skill_id}/versions", params=params)
        return wrap_page_response(r)

    def retrieve(self, version: str, *, skill_id: str) -> APIObject:
        r = self._sync.get(f"/v1/skills/{skill_id}/versions/{version}")
        return wrap_response(r)

    def delete(self, version: str, *, skill_id: str) -> APIObject:
        r = self._sync.delete(f"/v1/skills/{skill_id}/versions/{version}")
        return wrap_response(r)

    def download(self, version: str, *, skill_id: str) -> bytes:
        """Download version zip (``GET .../versions/{v}/content``)."""
        r = self._sync.get(f"/v1/skills/{skill_id}/versions/{version}/content")
        raise_for_status(r)
        return r.content

    def upload(
        self,
        skill_id: str,
        *,
        file: FileTuple | bytes | IO[bytes],
        display_title: str | None = None,
        filename: str = "skill.zip",
    ) -> APIObject:
        """OMA extension: multipart zip → ``.../versions/upload``."""
        fname, payload = _zip_parts(file, filename)
        data: dict[str, str] = {}
        if display_title:
            data["display_title"] = display_title
        r = self._sync.post(
            f"/v1/skills/{skill_id}/versions/upload",
            files={"file": (fname, io.BytesIO(payload), "application/zip")},
            data=data,
        )
        return wrap_response(r)

    # -- async --------------------------------------------------------------

    async def create_async(
        self,
        skill_id: str,
        *,
        files: list[dict[str, str]] | list[FileTuple] | None = None,
        display_title: str | None = None,
        description: str | None = None,
    ) -> APIObject:
        if files and len(files) == 1 and _is_zip_tuple(files[0]):
            return await self.upload_async(
                skill_id,
                file=files[0],  # type: ignore[arg-type]
                display_title=display_title,
            )
        body: dict[str, Any] = {"files": _normalize_json_files(files or [])}
        if display_title is not None:
            body["display_title"] = display_title
        if description is not None:
            body["description"] = description
        r = await self._http.post(f"/v1/skills/{skill_id}/versions", json=body)
        return wrap_response(r)

    async def list_async(self, skill_id: str, *, limit: int | None = None) -> SyncPage:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        r = await self._http.get(f"/v1/skills/{skill_id}/versions", params=params)
        return wrap_page_response(r)

    async def retrieve_async(self, version: str, *, skill_id: str) -> APIObject:
        r = await self._http.get(f"/v1/skills/{skill_id}/versions/{version}")
        return wrap_response(r)

    async def delete_async(self, version: str, *, skill_id: str) -> APIObject:
        r = await self._http.delete(f"/v1/skills/{skill_id}/versions/{version}")
        return wrap_response(r)

    async def download_async(self, version: str, *, skill_id: str) -> bytes:
        r = await self._http.get(
            f"/v1/skills/{skill_id}/versions/{version}/content"
        )
        raise_for_status(r)
        return r.content

    async def upload_async(
        self,
        skill_id: str,
        *,
        file: FileTuple | bytes | IO[bytes],
        display_title: str | None = None,
        filename: str = "skill.zip",
    ) -> APIObject:
        fname, payload = _zip_parts(file, filename)
        data: dict[str, str] = {}
        if display_title:
            data["display_title"] = display_title
        r = await self._http.post(
            f"/v1/skills/{skill_id}/versions/upload",
            files={"file": (fname, io.BytesIO(payload), "application/zip")},
            data=data,
        )
        return wrap_response(r)


class SkillsResource:
    """``client.skills`` — CMA-aligned sync API (+ ``*_async``)."""

    def __init__(self, http: httpx.AsyncClient, sync: httpx.Client) -> None:
        self._http = http
        self._sync = sync
        self.versions = SkillVersionsResource(http, sync)

    # -- CMA sync -----------------------------------------------------------

    def create(
        self,
        *,
        files: list[dict[str, str]] | list[FileTuple] | None = None,
        display_title: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> APIObject:
        """Create a skill (CMA: ``skills.create(files=..., display_title=...)``).

        A single ``(name.zip, bytes)`` file routes to ``POST /v1/skills/upload``.
        """
        if files and len(files) == 1 and _is_zip_tuple(files[0]):
            return self.upload(
                file=files[0],  # type: ignore[arg-type]
                display_title=display_title,
            )
        body: dict[str, Any] = {"files": _normalize_json_files(files or [])}
        if display_title is not None:
            body["display_title"] = display_title
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        r = self._sync.post("/v1/skills", json=body)
        return wrap_response(r)

    def list(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
    ) -> SyncPage:
        params: dict[str, Any] = {}
        if source is not None:
            params["source"] = source
        if limit is not None:
            params["limit"] = limit
        r = self._sync.get("/v1/skills", params=params)
        return wrap_page_response(r)

    def retrieve(self, skill_id: str) -> APIObject:
        r = self._sync.get(f"/v1/skills/{skill_id}")
        return wrap_response(r)

    def delete(self, skill_id: str) -> APIObject:
        r = self._sync.delete(f"/v1/skills/{skill_id}")
        return wrap_response(r)

    def upload(
        self,
        *,
        file: FileTuple | bytes | IO[bytes],
        display_title: str | None = None,
        filename: str = "skill.zip",
    ) -> APIObject:
        """OMA extension: multipart zip → ``POST /v1/skills/upload``."""
        fname, payload = _zip_parts(file, filename)
        data: dict[str, str] = {}
        if display_title:
            data["display_title"] = display_title
        r = self._sync.post(
            "/v1/skills/upload",
            files={"file": (fname, io.BytesIO(payload), "application/zip")},
            data=data,
        )
        return wrap_response(r)

    # -- async --------------------------------------------------------------

    async def create_async(
        self,
        *,
        files: list[dict[str, str]] | list[FileTuple] | None = None,
        display_title: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> APIObject:
        if files and len(files) == 1 and _is_zip_tuple(files[0]):
            return await self.upload_async(
                file=files[0],  # type: ignore[arg-type]
                display_title=display_title,
            )
        body: dict[str, Any] = {"files": _normalize_json_files(files or [])}
        if display_title is not None:
            body["display_title"] = display_title
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        r = await self._http.post("/v1/skills", json=body)
        return wrap_response(r)

    async def list_async(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
    ) -> SyncPage:
        params: dict[str, Any] = {}
        if source is not None:
            params["source"] = source
        if limit is not None:
            params["limit"] = limit
        r = await self._http.get("/v1/skills", params=params)
        return wrap_page_response(r)

    async def retrieve_async(self, skill_id: str) -> APIObject:
        r = await self._http.get(f"/v1/skills/{skill_id}")
        return wrap_response(r)

    async def delete_async(self, skill_id: str) -> APIObject:
        r = await self._http.delete(f"/v1/skills/{skill_id}")
        return wrap_response(r)

    async def upload_async(
        self,
        *,
        file: FileTuple | bytes | IO[bytes],
        display_title: str | None = None,
        filename: str = "skill.zip",
    ) -> APIObject:
        fname, payload = _zip_parts(file, filename)
        data: dict[str, str] = {}
        if display_title:
            data["display_title"] = display_title
        r = await self._http.post(
            "/v1/skills/upload",
            files={"file": (fname, io.BytesIO(payload), "application/zip")},
            data=data,
        )
        return wrap_response(r)
