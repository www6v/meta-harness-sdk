"""E2E tests for CMA-aligned FilesResource (sync primary + async variants)."""

from __future__ import annotations

import io
import os

import pytest

from sdk import OMAClient, NotFoundError
from sdk.examples import FileExamples


@pytest.fixture
def oma_client():
    os.environ.setdefault("OMA_API_KEY", "dev-key")
    client = OMAClient(base_url=os.getenv("OMA_BASE_URL", "http://127.0.0.1:8787"))
    yield client
    client.close()


def test_upload_multipart_retrieve_download_delete(oma_client: OMAClient):
    filename = "sdk-e2e-multipart.txt"
    payload = b"hello from sdk e2e multipart"

    uploaded = oma_client.files.upload(
        file=(filename, io.BytesIO(payload), "text/plain"),
        downloadable=True,
    )
    try:
        assert uploaded.id.startswith("file-")
        assert uploaded.filename == filename
        assert uploaded.mime_type == "text/plain"
        assert uploaded.size_bytes == len(payload)
        assert uploaded.downloadable is True

        got = oma_client.files.retrieve_metadata(uploaded.id)
        assert got.id == uploaded.id
        assert got.filename == filename

        assert oma_client.files.download(uploaded.id) == payload
        assert oma_client.files.content(uploaded.id) == payload
    finally:
        oma_client.files.delete(uploaded.id)


def test_upload_multipart_without_explicit_media_type(oma_client: OMAClient):
    filename = "sdk-e2e-no-mime.bin"
    payload = b"\x00\x01\x02\x03"

    uploaded = oma_client.files.upload(
        file=(filename, io.BytesIO(payload)),
        downloadable=True,
    )
    try:
        assert uploaded.id
        assert uploaded.filename == filename
        assert uploaded.mime_type in ("application/octet-stream", "text/plain")
        assert uploaded.size_bytes == len(payload)
    finally:
        oma_client.files.delete(uploaded.id)


def test_upload_json_string_csv(oma_client: OMAClient):
    filename = "sdk-e2e-json.csv"
    payload = "order_id,price\n1001,24.99\n1002,39.99\n"

    uploaded = oma_client.files.upload(
        filename=filename,
        content=payload,
        media_type="text/csv",
        downloadable=True,
    )
    try:
        assert uploaded.id
        assert uploaded.filename == filename
        assert uploaded.mime_type == "text/csv"
        assert uploaded.size_bytes == len(payload.encode("utf-8"))
        assert oma_client.files.download(uploaded.id).decode("utf-8") == payload
    finally:
        oma_client.files.delete(uploaded.id)


def test_upload_json_bytes_base64(oma_client: OMAClient):
    filename = "sdk-e2e-bytes.bin"
    payload = bytes(range(256))

    uploaded = oma_client.files.upload(
        filename=filename,
        content=payload,
        media_type="application/octet-stream",
        downloadable=True,
    )
    try:
        assert uploaded.id
        assert uploaded.size_bytes == len(payload)
        assert oma_client.files.download(uploaded.id) == payload
    finally:
        oma_client.files.delete(uploaded.id)


def test_list_files(oma_client: OMAClient):
    result = oma_client.files.list()
    assert isinstance(result.data, list)
    assert hasattr(result, "has_more")
    for f in result:
        assert f.id


def test_list_files_with_scope_id(oma_client: OMAClient):
    result = oma_client.files.list(scope_id="sess_does_not_exist")
    assert isinstance(result.data, list)


def test_list_by_scope_returns_uploaded_file(oma_client: OMAClient):
    scope = "sess-sdk-e2e-scope-test"
    filename = "sdk-e2e-scoped.txt"
    payload = b"scoped content"

    uploaded = oma_client.files.upload(
        file=(filename, io.BytesIO(payload), "text/plain"),
        scope_id=scope,
        downloadable=True,
    )
    try:
        result = oma_client.files.list(scope_id=scope)
        ids = [f.id for f in result]
        assert uploaded.id in ids
        scoped = next(f for f in result if f.id == uploaded.id)
        assert scoped.get("scope_id") == scope
    finally:
        oma_client.files.delete(uploaded.id)


def test_list_supports_limit_and_order(oma_client: OMAClient):
    result = oma_client.files.list(limit=5, order="asc")
    assert isinstance(result.data, list)
    assert len(result.data) <= 5


@pytest.mark.asyncio
async def test_file_examples_upload_multipart_and_retrieve(oma_client: OMAClient):
    result = FileExamples.upload_multipart_and_retrieve(oma_client)
    assert result["uploaded"]["id"]
    assert result["retrieved"]["id"] == result["uploaded"]["id"]
    assert result["downloaded"] == b"hello from sdk e2e"


@pytest.mark.asyncio
async def test_file_examples_upload_json_and_retrieve(oma_client: OMAClient):
    result = FileExamples.upload_json_and_retrieve(oma_client)
    assert result["uploaded"]["id"]
    assert result["downloaded"].decode("utf-8").startswith("order_id,price")


def test_upload_rejects_both_file_and_content(oma_client: OMAClient):
    with pytest.raises(ValueError, match="either 'file' or 'content'"):
        oma_client.files.upload(
            file=("a.txt", io.BytesIO(b"x"), "text/plain"),
            content="y",
        )


def test_upload_rejects_neither_file_nor_content(oma_client: OMAClient):
    with pytest.raises(ValueError, match="either 'file' or 'content'"):
        oma_client.files.upload()


def test_upload_json_requires_filename(oma_client: OMAClient):
    with pytest.raises(ValueError, match="filename"):
        oma_client.files.upload(content="hello")


def test_retrieve_unknown_file_returns_404(oma_client: OMAClient):
    with pytest.raises(NotFoundError):
        oma_client.files.retrieve("file_does_not_exist")
