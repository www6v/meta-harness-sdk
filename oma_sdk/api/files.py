"""Files resource — CMA-aligned sync API over OMA ``/v1/files``.

Matches Anthropic Managed Agents SDK shapes::

    client.files.upload(file=(name, f, \"text/csv\"))
    client.files.list(scope_id=session.id)
    client.files.download(file_id)          # raw bytes
    client.files.retrieve_metadata(file_id) # CMA name
    client.files.retrieve(file_id)          # alias
    client.files.delete(file_id)

Sync methods are the primary CMA surface (same as ``client.agents``).
Async variants use the ``*_async`` suffix for existing cookbook ``await`` calls.
"""

from __future__ import annotations

import base64 as _b64
import io
from typing import IO, Any

import httpx

from .._exceptions import raise_for_status
from .models_base import APIObject, SyncPage, wrap_page_response, wrap_response


class FilesResource:
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
                "sync FilesResource methods require OMAClient "
                "(constructed with a sync httpx.Client by default)"
            )
        return self._sync

    # -- CMA sync -----------------------------------------------------------

    def list(
        self,
        *,
        scope_id: str | None = None,
        limit: int | None = None,
        order: str | None = None,
        before_id: str | None = None,
        after_id: str | None = None,
        **extra_params: Any,
    ) -> SyncPage:
        params = _list_params(
            scope_id=scope_id,
            limit=limit,
            order=order,
            before_id=before_id,
            after_id=after_id,
            **extra_params,
        )
        r = self._require_sync().get("/v1/files", params=params)
        return wrap_page_response(r)

    def retrieve(self, file_id: str) -> APIObject:
        r = self._require_sync().get(f"/v1/files/{file_id}")
        return wrap_response(r)

    def retrieve_metadata(self, file_id: str) -> APIObject:
        """CMA alias for :meth:`retrieve`."""
        return self.retrieve(file_id)

    def upload(
        self,
        *,
        file: tuple[str, IO[bytes] | bytes] | tuple[str, IO[bytes] | bytes, str] | None = None,
        filename: str | None = None,
        content: bytes | str | None = None,
        media_type: str | None = None,
        encoding: str | None = None,
        scope_id: str | None = None,
        downloadable: bool = False,
    ) -> APIObject:
        """Upload a file (CMA: ``files.upload(file=(name, f, mime))``)."""
        mode = _upload_mode(file=file, content=content, filename=filename)
        sync = self._require_sync()
        if mode == "multipart":
            return _post_multipart_sync(
                sync,
                file=file,  # type: ignore[arg-type]
                media_type=media_type,
                scope_id=scope_id,
                downloadable=downloadable,
            )
        return _post_json_sync(
            sync,
            filename=filename,  # type: ignore[arg-type]
            content=content,  # type: ignore[arg-type]
            media_type=media_type,
            encoding=encoding,
            scope_id=scope_id,
            downloadable=downloadable,
        )

    def download(self, file_id: str) -> bytes:
        r = self._require_sync().get(f"/v1/files/{file_id}/content")
        raise_for_status(r)
        return r.content

    def content(self, file_id: str) -> bytes:
        """Alias for :meth:`download`."""
        return self.download(file_id)

    def delete(self, file_id: str) -> APIObject:
        r = self._require_sync().delete(f"/v1/files/{file_id}")
        return wrap_response(r)

    # -- async (cookbook) ---------------------------------------------------

    async def list_async(
        self,
        *,
        scope_id: str | None = None,
        limit: int | None = None,
        order: str | None = None,
        before_id: str | None = None,
        after_id: str | None = None,
        **extra_params: Any,
    ) -> SyncPage:
        params = _list_params(
            scope_id=scope_id,
            limit=limit,
            order=order,
            before_id=before_id,
            after_id=after_id,
            **extra_params,
        )
        r = await self._http.get("/v1/files", params=params)
        return wrap_page_response(r)

    async def retrieve_async(self, file_id: str) -> APIObject:
        r = await self._http.get(f"/v1/files/{file_id}")
        return wrap_response(r)

    async def upload_async(
        self,
        *,
        file: tuple[str, IO[bytes] | bytes] | tuple[str, IO[bytes] | bytes, str] | None = None,
        filename: str | None = None,
        content: bytes | str | None = None,
        media_type: str | None = None,
        encoding: str | None = None,
        scope_id: str | None = None,
        downloadable: bool = False,
    ) -> APIObject:
        mode = _upload_mode(file=file, content=content, filename=filename)
        if mode == "multipart":
            files, data = _multipart_body(
                file=file,  # type: ignore[arg-type]
                media_type=media_type,
                scope_id=scope_id,
                downloadable=downloadable,
            )
            r = await self._http.post("/v1/files", files=files, data=data)
            return wrap_response(r)
        body = _json_body(
            filename=filename,  # type: ignore[arg-type]
            content=content,  # type: ignore[arg-type]
            media_type=media_type,
            encoding=encoding,
            scope_id=scope_id,
            downloadable=downloadable,
        )
        r = await self._http.post("/v1/files", json=body)
        return wrap_response(r)

    async def download_async(self, file_id: str) -> bytes:
        r = await self._http.get(f"/v1/files/{file_id}/content")
        raise_for_status(r)
        return r.content

    async def content_async(self, file_id: str) -> bytes:
        return await self.download_async(file_id)

    async def delete_async(self, file_id: str) -> APIObject:
        r = await self._http.delete(f"/v1/files/{file_id}")
        return wrap_response(r)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _list_params(
    *,
    scope_id: str | None,
    limit: int | None,
    order: str | None,
    before_id: str | None,
    after_id: str | None,
    **extra_params: Any,
) -> dict[str, Any]:
    params: dict[str, Any] = dict(extra_params)
    if scope_id is not None:
        params["scope_id"] = scope_id
    if limit is not None:
        params["limit"] = limit
    if order is not None:
        params["order"] = order
    if before_id is not None:
        params["before_id"] = before_id
    if after_id is not None:
        params["after_id"] = after_id
    return params


def _upload_mode(*, file: Any, content: Any, filename: str | None) -> str:
    if file is not None and content is not None:
        raise ValueError("pass either 'file' or 'content', not both")
    if file is None and content is None:
        raise ValueError("pass either 'file' or 'content'")
    if file is not None:
        return "multipart"
    if filename is None:
        raise ValueError("'filename' is required for JSON upload")
    return "json"


def _as_file_obj(obj: IO[bytes] | bytes) -> IO[bytes]:
    if isinstance(obj, (bytes, bytearray)):
        return io.BytesIO(obj)
    return obj


def _multipart_body(
    *,
    file: tuple[str, IO[bytes] | bytes] | tuple[str, IO[bytes] | bytes, str],
    media_type: str | None,
    scope_id: str | None,
    downloadable: bool,
) -> tuple[dict[str, tuple[str, IO[bytes], str]], dict[str, str]]:
    if len(file) == 3:
        fname, fobj, mt = file  # type: ignore[misc]
    elif len(file) == 2:
        fname, fobj = file  # type: ignore[misc]
        mt = media_type or "application/octet-stream"
    else:
        raise ValueError(
            "'file' must be (filename, file_obj) or "
            "(filename, file_obj, media_type)"
        )
    if media_type is not None:
        mt = media_type
    files = {"file": (fname, _as_file_obj(fobj), mt)}
    data: dict[str, str] = {}
    if scope_id is not None:
        data["scope_id"] = scope_id
    if downloadable:
        data["downloadable"] = "true"
    return files, data


def _json_body(
    *,
    filename: str,
    content: bytes | str,
    media_type: str | None,
    encoding: str | None,
    scope_id: str | None,
    downloadable: bool,
) -> dict[str, Any]:
    if isinstance(content, bytes):
        text = _b64.b64encode(content).decode("ascii")
        default_encoding = "base64"
    else:
        text = content
        default_encoding = "utf8"
    body: dict[str, Any] = {
        "filename": filename,
        "content": text,
        "encoding": encoding or default_encoding,
        "downloadable": downloadable,
    }
    if media_type:
        body["media_type"] = media_type
    if scope_id is not None:
        body["scope_id"] = scope_id
    return body


def _post_multipart_sync(
    sync: httpx.Client,
    *,
    file: tuple[str, IO[bytes] | bytes] | tuple[str, IO[bytes] | bytes, str],
    media_type: str | None,
    scope_id: str | None,
    downloadable: bool,
) -> APIObject:
    files, data = _multipart_body(
        file=file,
        media_type=media_type,
        scope_id=scope_id,
        downloadable=downloadable,
    )
    r = sync.post("/v1/files", files=files, data=data)
    return wrap_response(r)


def _post_json_sync(
    sync: httpx.Client,
    *,
    filename: str,
    content: bytes | str,
    media_type: str | None,
    encoding: str | None,
    scope_id: str | None,
    downloadable: bool,
) -> APIObject:
    body = _json_body(
        filename=filename,
        content=content,
        media_type=media_type,
        encoding=encoding,
        scope_id=scope_id,
        downloadable=downloadable,
    )
    r = sync.post("/v1/files", json=body)
    return wrap_response(r)
