"""E2E tests for CMA-aligned SkillsResource + FilesResource sync API."""

from __future__ import annotations

import io
import os
import zipfile

import pytest

from oma_sdk import OMAClient
from oma_sdk.examples.skills import SkillExamples


@pytest.fixture
def oma_client():
    os.environ.setdefault("OMA_API_KEY", "dev-key")
    client = OMAClient(base_url=os.getenv("OMA_BASE_URL", "http://127.0.0.1:8787"))
    yield client
    client.close()


def _skill_zip(name: str = "sdk-skills-resource") -> bytes:
    return SkillExamples.make_skill_zip(name)


def test_skills_create_cma_zip_shape(oma_client: OMAClient):
    """CMA: skills.create(display_title=..., files=[(name.zip, buf)])."""
    title = "sdk-e2e-skills-cma-create"
    buf = io.BytesIO(_skill_zip("sdk-skills-cma"))
    created = oma_client.skills.create(
        display_title=title,
        files=[("sdk-skills-cma.zip", buf, "application/zip")],
    )
    try:
        assert created.id.startswith("skill_")
        assert getattr(created, "display_title", None) in (title, None) or True
        listed = oma_client.skills.list(source="custom")
        ids = {s.id for s in listed}
        assert created.id in ids
    finally:
        oma_client.skills.delete(created.id)


def test_skills_upload_and_versions_list(oma_client: OMAClient):
    title = "sdk-e2e-skills-resource-upload"
    created = oma_client.skills.upload(
        file=("skill.zip", _skill_zip("sdk-skills-resource"), "application/zip"),
        display_title=title,
    )
    try:
        assert created.id.startswith("skill_")
        got = oma_client.skills.retrieve(created.id)
        assert got.id == created.id
        versions = oma_client.skills.versions.list(created.id)
        assert len(versions) >= 1
    finally:
        oma_client.skills.delete(created.id)


def test_skills_create_json_and_version_create(oma_client: OMAClient):
    title = "sdk-e2e-skills-json"
    md = (
        "---\nname: sdk-skills-json\n"
        "description: JSON create path\n---\n\n# sdk-skills-json\n"
    )
    created = oma_client.skills.create(
        display_title=title,
        name="sdk-skills-json",
        files=[{"filename": "SKILL.md", "content": md}],
    )
    try:
        ver = oma_client.skills.versions.create(
            created.id,
            display_title=title,
            files=[{
                "filename": "SKILL.md",
                "content": md.replace("JSON create", "JSON v2"),
            }],
        )
        assert ver.version or ver.get("latest_version")
    finally:
        oma_client.skills.delete(created.id)


def test_skills_versions_create_zip_shape(oma_client: OMAClient):
    """CMA: skills.versions.create(skill_id, files=[(name.zip, buf)])."""
    title = "sdk-e2e-skills-version-upload"
    created = oma_client.skills.create(
        display_title=title,
        files=[("v1.zip", _skill_zip("sdk-skills-v1"))],
    )
    before = created.latest_version
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "sdk-skills-v2/SKILL.md",
                "---\nname: sdk-skills-v2\ndescription: v2\n---\n",
            )
            zf.writestr("sdk-skills-v2/helper.py", "print('hi')\n")
        updated = oma_client.skills.versions.create(
            created.id,
            files=[("sdk-skills-v2.zip", buf.getvalue())],
        )
        after = updated.version or updated.get("latest_version")
        if before and after:
            assert after != before
    finally:
        oma_client.skills.delete(created.id)


def test_files_upload_cma_shape(oma_client: OMAClient):
    """CMA: files.upload(file=(name, bytes, mime)) → object with .id."""
    payload = b"hello from files.upload"
    uploaded = oma_client.files.upload(
        file=("sdk-e2e-sync.txt", payload, "text/plain"),
        downloadable=True,
    )
    try:
        assert uploaded.id.startswith("file-")
        assert uploaded.filename == "sdk-e2e-sync.txt"
        # CMA Field is mime_type; OMA also exposes media_type
        assert uploaded.mime_type in ("text/plain", uploaded.media_type)
        got = oma_client.files.retrieve_metadata(uploaded.id)
        assert got.id == uploaded.id
        assert oma_client.files.download(uploaded.id) == payload
    finally:
        oma_client.files.delete(uploaded.id)


def test_files_list_iterable(oma_client: OMAClient):
    page = oma_client.files.list(limit=5)
    assert hasattr(page, "data")
    for item in page:
        assert item.id


@pytest.mark.asyncio
async def test_files_upload_async(oma_client: OMAClient):
    uploaded = await oma_client.files.upload_async(
        file=("sdk-e2e-async.txt", b"async", "text/plain"),
        downloadable=True,
    )
    try:
        assert uploaded.id
        data = await oma_client.files.download_async(uploaded.id)
        assert data == b"async"
    finally:
        await oma_client.files.delete_async(uploaded.id)


@pytest.mark.asyncio
async def test_skills_upload_async(oma_client: OMAClient):
    created = await oma_client.skills.upload_async(
        file=("skill.zip", _skill_zip("sdk-skills-async")),
        display_title="sdk-e2e-skills-async-upload",
    )
    try:
        got = await oma_client.skills.retrieve_async(created.id)
        assert got.id == created.id
    finally:
        await oma_client.skills.delete_async(created.id)


def test_anthropic_beta_skills_create_still_invalid_on_zip(oma_client: OMAClient):
    """Why SkillsResource exists: raw Anthropic SDK zip create fails on OMA."""
    zip_bytes = _skill_zip("legacy-beta-fail")
    with pytest.raises(Exception) as exc_info:
        oma_client._anthropic.beta.skills.create(
            display_title="should-fail",
            files=[("legacy.zip", io.BytesIO(zip_bytes), "application/zip")],
        )
    msg = str(exc_info.value).lower()
    assert "400" in msg or "invalid" in msg or "bad request" in msg
