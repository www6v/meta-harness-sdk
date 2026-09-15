"""
File Examples - High-level helpers for file operations (CMA-aligned sync API).

Uses ``client.files.upload`` / ``retrieve`` / ``download`` / ``delete`` —
same shapes as Anthropic ``client.beta.files.*``.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic import Anthropic as _Anthropic

_KEEP = os.getenv("OMA_KEEP_RESOURCES", "0") == "1"


def _id(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj["id"])
    return str(obj.id)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default) if hasattr(obj, key) else (
        obj.get(key, default) if hasattr(obj, "get") else default
    )


def _as_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


class FileExamples:
    """Example operations for files (upload / retrieve / download / delete)."""

    @staticmethod
    def _files(client: Any):
        files = getattr(client, "files", None)
        if files is not None:
            return files
        files = getattr(client, "_oma_files", None)
        if files is not None:
            return files
        return _HttpxFilesAdapter(client)

    @staticmethod
    def upload_multipart_and_retrieve(
        client: Any,
        *,
        filename: str = "sdk-e2e-upload.txt",
        payload: bytes = b"hello from sdk e2e",
        media_type: str = "text/plain",
    ) -> dict:
        """Upload via multipart, retrieve, download bytes (sync / CMA-shaped)."""
        files = FileExamples._files(client)
        uploaded = files.upload(
            file=(filename, io.BytesIO(payload), media_type),
            downloadable=True,
        )
        try:
            assert _id(uploaded)
            assert _get(uploaded, "filename") == filename
            assert _get(uploaded, "size_bytes") == len(payload)

            got = files.retrieve(_id(uploaded))
            assert _id(got) == _id(uploaded)
            assert _get(got, "filename") == filename

            downloaded = files.content(_id(uploaded))
            assert downloaded == payload

            return {
                "uploaded": _as_dict(uploaded),
                "retrieved": _as_dict(got),
                "downloaded": downloaded,
            }
        finally:
            if not _KEEP:
                try:
                    files.delete(_id(uploaded))
                except Exception:
                    pass
            else:
                print(
                    f"\n[KEEP] file {_id(uploaded)} ({filename}) — "
                    f"delete manually when done"
                )

    @staticmethod
    def upload_json_and_retrieve(
        client: Any,
        *,
        filename: str = "sdk-e2e-json-upload.csv",
        payload: str = "order_id,price\n1001,24.99\n1002,39.99\n",
        media_type: str = "text/csv",
    ) -> dict:
        files = FileExamples._files(client)
        uploaded = files.upload(
            filename=filename,
            content=payload,
            media_type=media_type,
            downloadable=True,
        )
        try:
            assert _id(uploaded)
            assert _get(uploaded, "filename") == filename
            assert _get(uploaded, "size_bytes") == len(payload.encode("utf-8"))

            got = files.retrieve(_id(uploaded))
            assert _id(got) == _id(uploaded)

            downloaded = files.content(_id(uploaded))
            assert downloaded.decode("utf-8") == payload

            return {
                "uploaded": _as_dict(uploaded),
                "retrieved": _as_dict(got),
                "downloaded": downloaded,
            }
        finally:
            if not _KEEP:
                try:
                    files.delete(_id(uploaded))
                except Exception:
                    pass
            else:
                print(
                    f"\n[KEEP] file {_id(uploaded)} ({filename}) — "
                    f"delete manually when done"
                )

    @staticmethod
    def list_files(client: Any) -> Any:
        files = FileExamples._files(client)
        result = files.list()
        data = getattr(result, "data", None)
        if data is None and isinstance(result, dict):
            data = result.get("data")
        assert isinstance(data, list)
        return result

    @staticmethod
    def list_by_session(client: Any, session_id: str) -> Any:
        files = FileExamples._files(client)
        result = files.list(scope_id=session_id)
        data = getattr(result, "data", None)
        if data is None and isinstance(result, dict):
            data = result.get("data")
        assert isinstance(data, list)
        return result

    @staticmethod
    def upload_from_path(
        client: Any,
        path: str | Path,
        *,
        media_type: str | None = None,
        scope_id: str | None = None,
    ) -> dict:
        p = Path(path)
        payload = p.read_bytes()
        mt = media_type or "application/octet-stream"
        files = FileExamples._files(client)
        uploaded = files.upload(
            file=(p.name, io.BytesIO(payload), mt),
            scope_id=scope_id,
            downloadable=True,
        )
        try:
            assert _id(uploaded)
            assert _get(uploaded, "size_bytes") == len(payload)
            return {"uploaded": _as_dict(uploaded), "path": str(p)}
        finally:
            if not _KEEP:
                try:
                    files.delete(_id(uploaded))
                except Exception:
                    pass

    # Keep async names as thin wrappers for older call sites.
    @staticmethod
    async def upload_multipart_and_retrieve_async(client: Any, **kwargs: Any) -> dict:
        return FileExamples.upload_multipart_and_retrieve(client, **kwargs)

    @staticmethod
    async def upload_json_and_retrieve_async(client: Any, **kwargs: Any) -> dict:
        return FileExamples.upload_json_and_retrieve(client, **kwargs)


class _HttpxFilesAdapter:
    """Minimal sync facade over a raw ``anthropic.Anthropic`` instance."""

    def __init__(self, client: "_Anthropic") -> None:
        self._client = client

    def _http(self):
        inner = getattr(self._client, "_client", None)
        if inner is None:
            raise RuntimeError("could not locate httpx client on anthropic.Anthropic")
        return inner

    def upload(self, **kwargs: Any) -> dict:
        import base64 as _b64

        client = self._http()
        file_tuple = kwargs.get("file")
        content = kwargs.get("content")

        if file_tuple is not None:
            if len(file_tuple) == 3:
                fname, fobj, mt = file_tuple  # type: ignore[misc]
            elif len(file_tuple) == 2:
                fname, fobj = file_tuple  # type: ignore[misc]
                mt = kwargs.get("media_type") or "application/octet-stream"
            else:
                raise ValueError(
                    "'file' must be (filename, file_obj) or "
                    "(filename, file_obj, media_type)"
                )
            files = {"file": (fname, fobj, mt)}
            data: dict[str, str] = {}
            if kwargs.get("scope_id"):
                data["scope_id"] = kwargs["scope_id"]
            if kwargs.get("downloadable"):
                data["downloadable"] = "true"
            req = client.build_request("POST", "/v1/files", files=files, data=data)
        elif content is not None:
            filename = kwargs.get("filename")
            if filename is None:
                raise ValueError("'filename' is required for JSON upload")
            if isinstance(content, bytes):
                text = _b64.b64encode(content).decode("ascii")
                enc = kwargs.get("encoding") or "base64"
            else:
                text = content
                enc = kwargs.get("encoding") or "utf8"
            body: dict[str, Any] = {
                "filename": filename,
                "content": text,
                "encoding": enc,
                "downloadable": bool(kwargs.get("downloadable", False)),
            }
            if kwargs.get("media_type"):
                body["media_type"] = kwargs["media_type"]
            if kwargs.get("scope_id"):
                body["scope_id"] = kwargs["scope_id"]
            req = client.build_request("POST", "/v1/files", json=body)
        else:
            raise ValueError("pass either 'file' or 'content'")

        resp = client.send(req)
        resp.raise_for_status()
        return resp.json()

    def retrieve(self, file_id: str) -> dict:
        client = self._http()
        req = client.build_request("GET", f"/v1/files/{file_id}")
        resp = client.send(req)
        resp.raise_for_status()
        return resp.json()

    def list(self, **params: Any) -> dict:
        client = self._http()
        req = client.build_request("GET", "/v1/files", params=params)
        resp = client.send(req)
        resp.raise_for_status()
        return resp.json()

    def content(self, file_id: str) -> bytes:
        client = self._http()
        req = client.build_request("GET", f"/v1/files/{file_id}/content")
        resp = client.send(req)
        resp.raise_for_status()
        return resp.content

    def download(self, file_id: str) -> bytes:
        return self.content(file_id)

    def delete(self, file_id: str) -> dict:
        client = self._http()
        req = client.build_request("DELETE", f"/v1/files/{file_id}")
        resp = client.send(req)
        resp.raise_for_status()
        return resp.json()
